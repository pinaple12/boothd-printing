from supabase import create_client, Client
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
import io
import util
from functools import lru_cache

from dotenv import load_dotenv
import os

load_dotenv('.env.local')

# credentials
url: str = 'https://fxpfrvfpgjqyermtbtwu.supabase.co'
key: str = os.getenv('KEY')
executor = ThreadPoolExecutor(max_workers=1)  # Limit concurrent uploads

def get_supabase_client():
    return create_client(url, key)

'''
stripId - integer id of the photostrip
templateId - integer id of the template being used
eventName - string representation of the event being served

This function creates and uploads requested photostrip to supabase
Returns:
    {code: 200, msg : "Success"}
    {code : 400, msg : "Descriptive Error Messsage"}
'''
def fetchTemplate(templateId):
    supabase = get_supabase_client()
    
    #retrieve template information from templateId
    try:
        templateInfo = (
            supabase.table('photo_templates')
            .select('*')
            .eq('id', templateId)
            .execute()
        ).data[0]
    except:
        return {"code" : 400, "msg" : f'Failed to find valid photo template under id {templateId}'}

    #retrieve template from storage
    try:
        templateRaw = (
            supabase.storage
            .from_('templates')
            .download(templateInfo['image_url'])
        )
    except:
        return {"code": 400, "msg": f"Failed to find valid photo template under image name {templateInfo['image_url']}"}

    #turn it into a cv2 object
    nparr = np.frombuffer(templateRaw, np.uint8)
    template = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return {"code" : 200, "msg" : "success", "data" : template}

def stripConstruction(stripId, photos, templateId, template, eventName, sessionId, uuid):
    #assigned filename to be uploaded as
    fileName = f'{stripId}'

    supabase = get_supabase_client()

    #retrieve template information from templateId
    try:
        templateInfo = (
            supabase.table('photo_templates')
            .select('*')
            .eq('id', templateId)
            .execute()
        ).data[0]
    except:
        return {"code" : 400, "msg" : f'Failed to find valid photo template under id {templateId}'}

    #get photo dimensions
    photoWidth = templateInfo['photo_width']
    photoHeight = templateInfo['photo_height']

    #get photo offsets and zip them
    pixelOffsets = list(zip(templateInfo['x_pixel_offsets'], templateInfo['y_pixel_offsets']))

    photostrip = util.create_strip(template, photos, pixelOffsets, photoWidth, photoHeight)

    #convert photostrip to png
    success, stripFile = cv2.imencode(".png", photostrip)
    
    executor.submit(upload_to_supabase, stripId, photos, eventName, sessionId, uuid, stripFile, fileName)

    return {"code" : 200, "msg" : "Success", "data" : stripFile}

def upload_to_supabase(stripId, photos, eventName, sessionId, uuid, stripFile, fileName):
    supabase = get_supabase_client()
    
    print(f"[INFO] Uploading strip to supabase for stripId: {stripId}")
    
    # Upload strip with retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = (
                supabase 
                .storage
                .from_('photos')
                .upload(file=stripFile.tobytes(), path=f'strips/{eventName}/{fileName}', file_options={"content-type" : "image/png"})
            )
            print(f"[SUCCESS] Strip uploaded to supabase for stripId: {stripId}")
            break
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[ERROR] Strip upload failure after {max_retries} attempts with error: {e}")
                return {"code": 400, "msg": f"Strip upload failed: {str(e)}"}
            else:
                print(f"[WARN] Retry {attempt + 1} for strip {stripId}")
                continue

    #array for saving photo names to upload
    photo_names = []
    print(f"[INFO] Uploading photos to supabase for stripId: {stripId}")
    
    # Upload individual photos with retry logic
    for count, photo in enumerate(photos):
        #prepare photos for saving
        photo_name = str(stripId) + '_' + str(count)
        photo_names.append(photo_name)
        success, photoFile = cv2.imencode(".png", photo)
        
        for attempt in range(max_retries):
            try:
                response = (
                    supabase.storage
                    .from_('photos')
                    .upload(file=photoFile.tobytes(), path=f'raw/{eventName}/{photo_name}', file_options={"content-type" : "image/png"})
                )
                print(f"[SUCCESS] Photo uploaded to supabase for stripId: {stripId}")
                break
            except Exception as e:
                if attempt == max_retries - 1:
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
            break
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[ERROR] Failed to insert into photo strips after {max_retries} attempts with error: {e}")
            else:
                print(f"[WARN] Retry {attempt + 1} for database update of strip {stripId}")
                continue

    return {"code": 200, "msg": "Success"}

#HARD CODED VARIABLES FOR TESTING:
#print(stripConstruction(1, 1, "test"))

# pics = util.generate_white_blocks()
# print(stripConstruction(2, pics, 1, "test", 1))