import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request


GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_DRIVE_FILES_URL = 'https://www.googleapis.com/drive/v3/files'
GOOGLE_DRIVE_UPLOAD_URL = 'https://www.googleapis.com/upload/drive/v3/files'
RESUMABLE_UPLOAD_MAX_ATTEMPTS = 3
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
    result = None
    for attempt in range(RESUMABLE_UPLOAD_MAX_ATTEMPTS):
        upload_url = _start_resumable_upload(
            access_token,
            metadata,
            source_mime_type,
            len(content),
        )
        try:
            try:
                result = _upload_content(
                    upload_url,
                    access_token,
                    source_mime_type,
                    content,
                    start=0,
                )
            except GoogleDriveError as exc:
                if not _is_resumable_upload_error(exc):
                    raise
                result = _resume_upload(
                    upload_url,
                    access_token,
                    source_mime_type,
                    content,
                    exc,
                )
            break
        except GoogleDriveError as exc:
            if (
                not _is_expired_upload_session_error(exc)
                or attempt == RESUMABLE_UPLOAD_MAX_ATTEMPTS - 1
            ):
                raise
            logger.info(
                'Google Drive upload session expired with HTTP %s; starting a new session.',
                exc.status_code,
            )

    if result is None:
        raise GoogleDriveError('Google Drive upload did not complete.')
    file_id = result.get('id')
    if not isinstance(file_id, str) or not file_id:
        raise GoogleDriveError('Google Drive did not return a file ID.')
    return file_id, _google_view_link(result.get('webViewLink'))


def _start_resumable_upload(access_token, metadata, source_mime_type, content_length):
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
            'X-Upload-Content-Length': str(content_length),
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
    return upload_url


def _upload_content(upload_url, access_token, source_mime_type, content, *, start):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': source_mime_type,
        'Content-Length': str(len(content) - start),
    }
    if start:
        headers['Content-Range'] = f'bytes {start}-{len(content) - 1}/{len(content)}'
    request = urllib.request.Request(
        upload_url,
        data=content[start:],
        headers=headers,
        method='PUT',
    )
    return _request_json(request)


def _resume_upload(upload_url, access_token, source_mime_type, content, initial_error):
    last_error = initial_error
    for attempt in range(RESUMABLE_UPLOAD_MAX_ATTEMPTS):
        if attempt:
            time.sleep(2 ** (attempt - 1))
        try:
            result, range_header = _query_upload_status(
                upload_url,
                access_token,
                len(content),
            )
        except GoogleDriveError as exc:
            if (
                not _is_resumable_upload_error(exc)
                or attempt == RESUMABLE_UPLOAD_MAX_ATTEMPTS - 1
            ):
                raise
            last_error = exc
            continue
        if result is not None:
            return result

        start = _upload_offset(range_header, len(content))
        if start == len(content):
            continue
        try:
            return _upload_content(
                upload_url,
                access_token,
                source_mime_type,
                content,
                start=start,
            )
        except GoogleDriveError as exc:
            if not _is_resumable_upload_error(exc) and exc.status_code != 308:
                raise
            last_error = exc

    raise last_error


def _query_upload_status(upload_url, access_token, content_length):
    request = urllib.request.Request(
        upload_url,
        data=b'',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Length': '0',
            'Content-Range': f'bytes */{content_length}',
        },
        method='PUT',
    )
    with _open_google_request(request, allow_incomplete=True) as response:
        if response.code == 308:
            return None, response.headers.get('Range')
        try:
            result = json.loads(response.read().decode('utf-8'))
        except json.JSONDecodeError as exc:
            raise GoogleDriveError('Google Drive returned an invalid response.') from exc
    if not isinstance(result, dict):
        raise GoogleDriveError('Google Drive returned an invalid response.')
    return result, None


def _upload_offset(range_header, content_length):
    if range_header is None:
        return 0
    prefix = 'bytes=0-'
    if not range_header.startswith(prefix):
        raise GoogleDriveError('Google Drive returned an invalid upload range.')
    try:
        offset = int(range_header[len(prefix):]) + 1
    except ValueError as exc:
        raise GoogleDriveError('Google Drive returned an invalid upload range.') from exc
    if offset > content_length:
        raise GoogleDriveError('Google Drive returned an invalid upload range.')
    return offset


def _is_resumable_upload_error(error):
    return error.status_code is None or 500 <= error.status_code < 600


def _is_expired_upload_session_error(error):
    return error.status_code is not None and 400 <= error.status_code < 500


def _request_json(request, *, authorization_error=False):
    with _open_google_request(request, authorization_error=authorization_error) as response:
        try:
            result = json.loads(response.read().decode('utf-8'))
        except json.JSONDecodeError as exc:
            raise GoogleDriveError('Google Drive returned an invalid response.') from exc

    if not isinstance(result, dict):
        raise GoogleDriveError('Google Drive returned an invalid response.')
    return result


def _open_google_request(
    request,
    *,
    authorization_error=False,
    allow_incomplete=False,
):
    try:
        return urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        if allow_incomplete and exc.code == 308:
            return exc
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
