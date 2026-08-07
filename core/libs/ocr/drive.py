import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def get_drive_service(creds):
    return build('drive', 'v3', credentials=creds)

def upload_image_as_doc(service, image_path):
    """
    Upload file ảnh lên Google Drive và tự động convert sang Google Docs (chính là bước OCR).
    Trả về file_id của Google Docs.
    """
    filename = os.path.basename(image_path)
    file_metadata = {
        'name': filename,
        'mimeType': 'application/vnd.google-apps.document' # Tự động convert sang Google Docs
    }
    
    media = MediaFileUpload(image_path, mimetype='image/jpeg', resumable=True)
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    
    return file.get('id')

def delete_file(service, file_id):
    """
    Xóa file trên Google Drive theo file_id.
    """
    try:
        service.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        print(f"[Cảnh báo] Không thể xóa file ID {file_id}: {e}")
        return False
