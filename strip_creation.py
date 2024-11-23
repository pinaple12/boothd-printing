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

    photostrip = util.create_strip(template, photos, pixelOffsets, photoWidth, photoHeight)

    # Convert photostrip to jpeg with 80% quality
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, 90]
    success, stripFile = cv2.imencode(".jpg", photostrip, encode_params)
    
    executor.submit(upload_to_supabase, stripId, photos, eventName, sessionId, uuid, stripFile, fileName)
    
    return {"code": 200, "msg": "Success", "data": stripFile}

def upload_to_supabase(stripId, photos, eventName, sessionId, uuid, stripFile, fileName):
    supabase = get_supabase_client()
    errors_occurred = False  # Flag to track errors
    
    print(f"[INFO] Uploading strip to supabase for stripId: {stripId}")
    
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
            print(f"[SUCCESS] Strip uploaded to supabase for stripId: {stripId}")
            break
        except Exception as e:
            if attempt == max_retries - 1:
                errors_occurred = True
                print(f"[ERROR] Strip upload failure after {max_retries} attempts with error: {e}")
                return {"code": 400, "msg": f"Strip upload failed: {str(e)}"}
            else:
                print(f"[WARN] Retry {attempt + 1} for strip {stripId}")
                continue

    # Array for saving photo names to upload
    photo_names = []
    print(f"[INFO] Uploading photos to supabase for stripId: {stripId}")
    
    # Upload individual photos with retry logic
    for count, photo in enumerate(photos):
        photo_name = f"{stripId}_{count}"
        photo_names.append(photo_name)
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 90]  # 80% quality JPEG
        success, photoFile = cv2.imencode(".jpg", photo, encode_params)
        if not success:
            print(f"[ERROR] Failed to encode photo {photo_name}")
            continue
        
        for attempt in range(max_retries):
            try:
                response = (
                    supabase.storage
                    .from_('photos')
                    .upload(file=photoFile.tobytes(), path=f'raw/{eventName}/{photo_name}', file_options={"content-type": "image/jpeg"})  # Changed content-type to jpeg
                )
                print(f"[SUCCESS] Photo {photo_name} uploaded to supabase for stripId: {stripId}")
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    errors_occurred = True
                    print(f"[ERROR] Photo upload failure after {max_retries} attempts with error: {e}")
                else:
                    print(f"[WARN] Retry {attempt + 1} for photo {photo_name}")
                    continue

    # Update database with retry logic
    for attempt in range(max_retries):
        try:
            response = (
                supabase.table("photo_strips")
                .upsert({"uuid": uuid, "id": stripId, "session_id": sessionId, "image_url": fileName, "raw_photos": photo_names})
                .execute()
            )
            print(f"[SUCCESS] Database updated for stripId: {stripId}")
            break
        except Exception as e:
            if attempt == max_retries - 1:
                errors_occurred = True
                print(f"[ERROR] Failed to insert into photo strips after {max_retries} attempts with error: {e}")
            else:
                print(f"[WARN] Retry {attempt + 1} for database update of strip {stripId}")
                continue

    # When all is said and done, let's text the user that their photostrip is ready
    if not errors_occurred:
        # Fetch phone numbers associated with the strip
        try:
            response = supabase.table("sms_notification").select("phone").eq("for_strip", stripId).execute()
            data = response.data
            if data and len(data) > 0:
                print(f"[INFO] Sending SMS notifications for stripId: {stripId} to {len(data)} users")
                for entry in data:
                    phone_number = entry["phone"]
                    print(f"[INFO] Sending SMS to {phone_number} from {twilio_phone_number}")
                    try:
                        # ---------- Turning off until we are verified -----------
                        # twilio_client.messages.create(
                        #     body="Your photos are ready!",
                        #     to=phone_number,
                        #     from_=twilio_phone_number
                        # )
                        print(f"[SUCCESS] Message sent to {phone_number}")
                    except Exception as e:
                        print(f"[ERROR] Error sending message to {phone_number}: {e}")
            else:
                print(f"[INFO] No phone numbers found for stripId: {stripId}")
        except Exception as e:
            print(f"[ERROR] Error fetching phone numbers: {e}")
    else:
        print(f"[INFO] Skipping SMS notification due to earlier errors for stripId: {stripId}")
    
    return {"code": 200, "msg": "Success"}

# Example usage
# pics = util.generate_white_blocks()
# result = stripConstruction(2, pics, 1, template, "test_event", 1, "unique_uuid")
# print(result)