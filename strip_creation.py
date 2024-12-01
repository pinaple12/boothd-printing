from supabase import create_client, Client
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
import io
import util
from functools import lru_cache
from twilio.rest import Client as TwilioClient

from dotenv import load_dotenv
import os

load_dotenv('.env.local')

# Supabase credentials
url: str = 'https://fxpfrvfpgjqyermtbtwu.supabase.co'
key: str = os.getenv('KEY')
executor = ThreadPoolExecutor(max_workers=1)  # Limit concurrent uploads

# Twilio credentials
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_SECRET")
twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")
twilio_client = TwilioClient(account_sid, auth_token)

# Add color constants at the top of the file
RED = '\033[91m'      # Bright red for errors
GREEN = '\033[92m'    # Bright green for success
YELLOW = '\033[93m'   # Bright yellow for warnings
BLUE = '\033[94m'     # Bright blue for important info
MAGENTA = '\033[95m'  # Bright magenta for print operations
CYAN = '\033[96m'     # Bright cyan for important info
GRAY = '\033[90m'     # Dim gray for less important info
BOLD = '\033[1m'
ENDC = '\033[0m'

def get_supabase_client():
    return create_client(url, key)

def fetchTemplate(templateId):
    supabase = get_supabase_client()
    
    # Retrieve template information from templateId
    try:
        templateInfo = (
            supabase.table('photo_templates')
            .select('*')
            .eq('id', templateId)
            .execute()
        ).data[0]
    except Exception as e:
        return {"code": 400, "msg": f'Failed to find valid photo template under id {templateId}', "error": str(e)}

    # Retrieve template from storage
    try:
        templateRaw = (
            supabase.storage
            .from_('templates')
            .download(templateInfo['image_url'])
        )
    except Exception as e:
        return {"code": 400, "msg": f"Failed to find valid photo template under image name {templateInfo['image_url']}", "error": str(e)}

    # Turn it into a cv2 object
    nparr = np.frombuffer(templateRaw, np.uint8)
    template = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return {"code": 200, "msg": "success", "data": template}

def stripConstruction(stripId, photos, templateId, template, eventName, sessionId, uuid):
    # Assigned filename to be uploaded as
    fileName = f'{stripId}'

    supabase = get_supabase_client()

    # Retrieve template information from templateId
    try:
        templateInfo = (
            supabase.table('photo_templates')
            .select('*')
            .eq('id', templateId)
            .execute()
        ).data[0]
    except Exception as e:
        return {"code": 400, "msg": f'Failed to find valid photo template under id {templateId}', "error": str(e)}

    # Get photo dimensions
    photoWidth = templateInfo['photo_width']
    photoHeight = templateInfo['photo_height']

    # Get photo offsets and zip them
    pixelOffsets = list(zip(templateInfo['x_pixel_offsets'], templateInfo['y_pixel_offsets']))

    print(f"{BLUE}[STRIP] Creating photostrip for ID: {stripId}{ENDC}")
    photostrip = util.create_strip(template, photos, pixelOffsets, photoWidth, photoHeight)

    # Convert photostrip to jpeg with 80% quality
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, 90]
    success, stripFile = cv2.imencode(".jpg", photostrip, encode_params)
    
    executor.submit(upload_to_supabase, stripId, photos, eventName, sessionId, uuid, stripFile, fileName)
    print(f"{GREEN}[STRIP] Photostrip created successfully{ENDC}")
    
    return {"code": 200, "msg": "Success", "data": stripFile}

def upload_to_supabase(stripId, photos, eventName, sessionId, uuid, stripFile, fileName):
    supabase = get_supabase_client()
    errors_occurred = False  # Flag to track errors
    
    print(f"{GRAY}[UPLOAD] Starting upload for stripId: {stripId}{ENDC}")
    
    # Upload strip with retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = (
                supabase 
                .storage
                .from_('photos')
                .upload(file=stripFile.tobytes(), path=f'strips/{eventName}/{fileName}', file_options={"content-type": "image/jpeg"})
            )
            print(f"{GRAY}[UPLOAD] Strip uploaded successfully{ENDC}")
            break
        except Exception as e:
            if attempt == max_retries - 1:
                errors_occurred = True
                print(f"{RED}[ERROR] Strip upload failed after {max_retries} attempts: {e}{ENDC}")
                return {"code": 400, "msg": f"Strip upload failed: {str(e)}"}
            else:
                print(f"{YELLOW}[RETRY] Attempt {attempt + 1} for strip upload{ENDC}")
                continue

    # Array for saving photo names to upload
    photo_names = []
    print(f"{GRAY}[UPLOAD] Processing individual photos...{ENDC}")
    
    # Upload individual photos with retry logic
    for count, photo in enumerate(photos):
        photo_name = f"{stripId}_{count}"
        photo_names.append(photo_name)
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 90]
        success, photoFile = cv2.imencode(".jpg", photo, encode_params)
        if not success:
            print(f"{RED}[ERROR] Failed to encode photo {photo_name}{ENDC}")
            continue
        
        for attempt in range(max_retries):
            try:
                response = (
                    supabase.storage
                    .from_('photos')
                    .upload(file=photoFile.tobytes(), path=f'raw/{eventName}/{photo_name}', file_options={"content-type": "image/jpeg"})
                )
                print(f"{GRAY}[UPLOAD] Photo {count + 1} uploaded{ENDC}")
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    errors_occurred = True
                    print(f"{RED}[ERROR] Photo {count + 1} upload failed: {e}{ENDC}")
                else:
                    print(f"{YELLOW}[RETRY] Attempt {attempt + 1} for photo {count + 1}{ENDC}")
                    continue

    # Update database with retry logic
    for attempt in range(max_retries):
        try:
            response = (
                supabase.table("photo_strips")
                .upsert({"uuid": uuid, "id": stripId, "session_id": sessionId, "image_url": fileName, "raw_photos": photo_names})
                .execute()
            )
            print(f"{GRAY}[UPLOAD] Database updated{ENDC}")
            break
        except Exception as e:
            if attempt == max_retries - 1:
                errors_occurred = True
                print(f"{RED}[ERROR] Database update failed: {e}{ENDC}")
            else:
                print(f"{YELLOW}[RETRY] Attempt {attempt + 1} for database update{ENDC}")
                continue

    # SMS notifications
    if not errors_occurred:
        try:
            response = supabase.table("sms_notification").select("phone").eq("for_strip", stripId).execute()
            data = response.data
            if data and len(data) > 0:
                print(f"{BLUE}[SMS] Sending notifications to {len(data)} recipients{ENDC}")
                for entry in data:
                    phone_number = entry["phone"]
                    try:
                        # SMS sending code commented out
                        print(f"{GREEN}[SMS] Notification ready for {phone_number}{ENDC}")
                    except Exception as e:
                        print(f"{RED}[ERROR] SMS failed for {phone_number}: {e}{ENDC}")
            else:
                print(f"{GRAY}[SMS] No notifications requested{ENDC}")
        except Exception as e:
            print(f"{RED}[ERROR] SMS lookup failed: {e}{ENDC}")
    else:
        print(f"{YELLOW}[WARN] Skipping notifications due to upload errors{ENDC}")
    
    if not errors_occurred:
        print(f"{GREEN}[SUCCESS] All operations completed for strip {stripId}{ENDC}")
    
    return {"code": 200, "msg": "Success"}

# Example usage
# pics = util.generate_white_blocks()
# result = stripConstruction(2, pics, 1, template, "test_event", 1, "unique_uuid")
# print(result)