from supabase import create_client, Client
import cv2
import numpy as np
import io
import util

from dotenv import load_dotenv
import os

load_dotenv('.env.local')

#credentials
url: str = 'https://fxpfrvfpgjqyermtbtwu.supabase.co'
key: str = os.getenv('KEY')
supabase: Client = create_client(url, key)

'''
stripId - integer id of the photostrip
templateId - integer id of the template being used
eventName - string representation of the event being served

This function creates and uploads requested photostrip to supabase
Returns:
    {code: 200, msg : "Success"}
    {code : 400, msg : "Descriptive Error Messsage"}
'''
#new plan: i have an array of photos, a templateId, and an eventName
#i will everything to supabase
def stripConstruction(stripId, photos, templateId, eventName, sessionId, uuid):

    #assigned filename to be uploaded as
    fileName = f'{stripId}'

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

    #get photo dimensions
    photoWidth = templateInfo['photo_width']
    photoHeight = templateInfo['photo_height']

    #get photo offsets and zip them
    pixelOffsets = list(zip(templateInfo['x_pixel_offsets'], templateInfo['y_pixel_offsets']))

    photostrip = util.create_strip(template, photos, pixelOffsets, photoWidth, photoHeight)

    #convert photostrip to png
    success, stripFile = cv2.imencode(".png", photostrip)
    try:
        #upload to supabase
        #IMPORTANT : duplicate filename will FAIL
        (
            supabase
            .storage
            .from_('photos')
            .upload(file=stripFile.tobytes(), path=f'strips/{eventName}/{fileName}', file_options={"content-type" : "image/png"})
         )
    except:
        return {"code" : 400, "msg" : "Strip upload failure"}

    #array for saving photo names to upload
    photo_names = []
    for count, photo in enumerate(photos):
        #prepare photos for saving
        photo_name = str(stripId) + '_' + str(count)
        photo_names.append(photo_name)
        success, photoFile = cv2.imencode(".png", photo)
        try:
            (
                supabase.storage
                .from_('photos')
                .upload(file=photoFile.tobytes(), path=f'raw/{eventName}/{photo_name}', file_options={"content-type" : "image/png"})
            )
        except Exception as e:
            print(e)
            return {"code" : 400, "msg" : "Photo upload failure"}

    try:
        (
            supabase.table("photo_strips")
            .upsert({"uuid": uuid, "id" : stripId, "session_id" : sessionId, "image_url" : fileName, "raw_photos" : photo_names})
            .execute()
        )
    except Exception as e:
        print(e)
        return{"code" : 400, "msg" : "Failed to insert into photo strips"}


    return {"code" : 200, "msg" : "Success", "data" : stripFile}


#HARD CODED VARIABLES FOR TESTING:
#print(stripConstruction(1, 1, "test"))

# pics = util.generate_white_blocks()
# print(stripConstruction(2, pics, 1, "test", 1))
