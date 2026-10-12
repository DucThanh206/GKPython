import json
import logging
import urllib.error
import urllib.parse
import urllib.request


GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_DRIVE_FILES_URL = 'https://www.googleapis.com/drive/v3/files'
GOOGLE_DRIVE_UPLOAD_URL = 'https://www.googleapis.com/upload/drive/v3/files'
logger = logging.getLogger(__name__)


class GoogleDriveError(Exception):
    def __init__(self, message, *, status_code=None, reason=None):
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


class GoogleDriveAuthorizationError(GoogleDriveError):
    pass


def _google_view_link(value):
    if not isinstance(value, str) or not value:
        raise GoogleDriveError('Google Drive did not return an open link.')
    try:
        parsed = urllib.parse.urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise GoogleDriveError('Google Drive returned an invalid open link.') from exc
    if (
        parsed.scheme != 'https'
        or parsed.hostname not in {
            'docs.google.com',
            'drive.google.com',
            'sheets.google.com',
            'slides.google.com',
        }
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        raise GoogleDriveError('Google Drive returned an invalid open link.')
    return value


def refresh_access_token(refresh_token, client_id, client_secret):
    body = urllib.parse.urlencode(
        {
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }
    ).encode('utf-8')
    request = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    result = _request_json(request, authorization_error=True)
    access_token = result.get('access_token')
    if not isinstance(access_token, str) or not access_token:
        raise GoogleDriveError('Google did not return an access token.')
    return access_token


def get_existing_file_link(access_token, file_id):
    url = (
        f'{GOOGLE_DRIVE_FILES_URL}/{urllib.parse.quote(file_id, safe="")}?'
        f'{urllib.parse.urlencode({"fields": "id,webViewLink"})}'
    )
    request = urllib.request.Request(
        url,
        headers={'Authorization': f'Bearer {access_token}'},
    )
    try:
        result = _request_json(request)
    except GoogleDriveError as exc:
        if getattr(exc, 'status_code', None) == 404:
            return None
        raise
    return _google_view_link(result.get('webViewLink'))


def upload_file(access_token, filename, source_mime_type, target_mime_type, content):
    metadata = json.dumps(
        {'name': filename, 'mimeType': target_mime_type},
        ensure_ascii=False,
    ).encode('utf-8')
    query = urllib.parse.urlencode(
        {'uploadType': 'resumable', 'fields': 'id,webViewLink'}
    )
    initiation_request = urllib.request.Request(
        f'{GOOGLE_DRIVE_UPLOAD_URL}?{query}',
        data=metadata,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json; charset=UTF-8',
            'X-Upload-Content-Type': source_mime_type,
            'X-Upload-Content-Length': str(len(content)),
        },
        method='POST',
    )
    with _open_google_request(initiation_request) as response:
        upload_url = response.headers.get('Location')
    if not upload_url:
        raise GoogleDriveError('Google Drive did not return an upload session.')
    try:
        parsed_upload_url = urllib.parse.urlparse(upload_url)
        upload_port = parsed_upload_url.port
    except ValueError as exc:
        raise GoogleDriveError('Google Drive returned an invalid upload session.') from exc
    if (
        parsed_upload_url.scheme != 'https'
        or parsed_upload_url.hostname != 'www.googleapis.com'
        or upload_port not in (None, 443)
    ):
        raise GoogleDriveError('Google Drive returned an invalid upload session.')

    upload_request = urllib.request.Request(
        upload_url,
        data=content,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': source_mime_type,
            'Content-Length': str(len(content)),
        },
        method='PUT',
    )
    result = _request_json(upload_request)
    file_id = result.get('id')
    if not isinstance(file_id, str) or not file_id:
        raise GoogleDriveError('Google Drive did not return a file ID.')
    return file_id, _google_view_link(result.get('webViewLink'))


def _request_json(request, *, authorization_error=False):
    with _open_google_request(request, authorization_error=authorization_error) as response:
        try:
            result = json.loads(response.read().decode('utf-8'))
        except json.JSONDecodeError as exc:
            raise GoogleDriveError('Google Drive returned an invalid response.') from exc

    if not isinstance(result, dict):
        raise GoogleDriveError('Google Drive returned an invalid response.')
    return result


def _open_google_request(request, *, authorization_error=False):
    try:
        return urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode('utf-8', errors='replace')
        try:
            error_data = json.loads(details)
        except json.JSONDecodeError:
            error_data = {}
        if not isinstance(error_data, dict):
            error_data = {}
        error = error_data.get('error', {})
        if isinstance(error, dict):
            api_status = error.get('status')
            error_code = error.get('error')
            error_details = error.get('errors', [])
            reason = (
                error_details[0].get('reason')
                if error_details and isinstance(error_details[0], dict)
                else None
            )
            error_code = reason or error_code or api_status
            message = error.get('message') or str(error_code or 'Google Drive request failed.')
        else:
            error_code = error
            api_status = None
            reason = error if isinstance(error, str) else None
            message = str(error or 'Google Drive request failed.')
        if authorization_error and error_code == 'invalid_grant':
            raise GoogleDriveAuthorizationError(
                'Google Drive authorization expired or was revoked.'
            ) from exc
        raise GoogleDriveError(
            message,
            status_code=exc.code,
            reason=reason or api_status,
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning('Google Drive request failed: %s', exc)
        raise GoogleDriveError('Could not communicate with Google Drive.') from exc
