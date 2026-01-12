import os
import requests
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Load environment variables from .env file
load_dotenv()

# Get img.bb API key from environment variable
IMG_BB_API_KEY = os.getenv('IMG_BB_API_KEY')

def upload_to_imgbb(image_file, filename=None):
    """
    Upload an image to img.bb
    
    Args:
        image_file: File object from request.files
        filename: Optional custom filename
        
    Returns:
        dict: Dictionary containing 'url' and 'delete_url' if successful, None otherwise
    """
    if not IMG_BB_API_KEY:
        print("Warning: IMG_BB_API_KEY not set. Image upload disabled.")
        return None
    
    if not filename:
        filename = secure_filename(image_file.filename)
    
    try:
        # Read the image file
        image_data = image_file.read()
        
        # Prepare the request
        url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": IMG_BB_API_KEY,
            "name": filename,
            "expiration": 0  # 0 = never expire
        }
        files = {
            "image": (f"{filename}", image_data, image_file.mimetype)
        }
        
        # Upload the image
        response = requests.post(url, data=payload, files=files)
        response.raise_for_status()
        
        # Return the upload result
        result = response.json()
        if result.get('success'):
            return {
                'url': result['data']['url'],
                'delete_url': result['data']['delete_url'],
                'thumb_url': result['data']['thumb']['url'] if 'thumb' in result['data'] else result['data']['url']
            }
        return None
        
    except Exception as e:
        print(f"Error uploading image to img.bb: {str(e)}")
        return None
