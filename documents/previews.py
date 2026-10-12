from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


DOCX_DOCUMENT_PATH = 'word/document.xml'
WORD_NAMESPACE = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
TEXT_EXTENSIONS = {'.txt', '.md', '.csv'}


def extract_docx_text(content):
    with ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read(DOCX_DOCUMENT_PATH)

    root = ElementTree.fromstring(document_xml)
    paragraphs = []
    for paragraph in root.findall('.//w:p', WORD_NAMESPACE):
        parts = []
        for node in paragraph.iter():
            if node.tag == f'{{{WORD_NAMESPACE["w"]}}}t':
                parts.append(node.text or '')
            elif node.tag == f'{{{WORD_NAMESPACE["w"]}}}tab':
                parts.append('\t')
            elif node.tag in (
                f'{{{WORD_NAMESPACE["w"]}}}br',
                f'{{{WORD_NAMESPACE["w"]}}}cr',
            ):
                parts.append('\n')
        text = ''.join(parts)
        paragraphs.append(text)
    return '\n'.join(paragraphs)


def get_plain_text(content):
    return content.decode('utf-8-sig')


__all__ = [
    'BadZipFile',
    'ElementTree',
    'TEXT_EXTENSIONS',
    'extract_docx_text',
    'get_plain_text',
]
