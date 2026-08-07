from googleapiclient.discovery import build

def get_docs_service(creds):
    return build('docs', 'v1', credentials=creds)

def read_doc_text(service, document_id):
    """
    Đọc toàn bộ nội dung văn bản trong Google Docs (đã được Google OCR từ ảnh).
    """
    document = service.documents().get(documentId=document_id).execute()
    text = ""
    for value in document.get('body').get('content'):
        if 'paragraph' in value:
            elements = value.get('paragraph').get('elements')
            for elem in elements:
                if 'textRun' in elem:
                    text += elem.get('textRun').get('content')
    
    # Text trả về có thể bao gồm khoảng trắng và ký tự newline dư thừa
    text = text.strip()
    
    # Rất quan trọng: Google Docs luôn chèn Tên File (vd: 0_00_10__...jpeg) vào đầu văn bản.
    # Ta phải mô phỏng lại logic cắt dòng của bản 2017 để loại bỏ tên file này.
    lines = text.split('\n')
    # Bỏ qua các dòng trống ở đầu và dòng chứa tên file
    clean_lines = []
    for line in lines:
        if ('.jpeg' in line or '.jpg' in line or '.png' in line) and len(line) < 100:
            continue
        clean_lines.append(line)
        
    return '\n'.join(clean_lines).strip()
