from supabase import create_client, Client
import cv2
import numpy as np
import io
import util

#credentials
url: str = 'https://fxpfrvfpgjqyermtbtwu.supabase.co'
key: str = 'SECRET-KEY'
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
def stripConstruction(stripId, templateId, eventName):

    #array of photos to be put in the strip
    photos = []
    photoNames = []

    #assigned filename to be uploaded as
    fileName = ''

    #query supabase for raw photos under stripId
    try:
        photoQueryResponse = (
                supabase.table('photo_strips')
                .select('raw_photos', 'image_url')
                .eq('id', stripId)
                .execute()
            )
    except:
        return {"code" : 400, "msg" : f'Failed to fetch stripId {stripId} from photo_strips in supabase'}
    

    if photoQueryResponse.count == 0:
        return {"code" : 400, "msg" : f'Failed to find valid photos under stripId {stripId} from photo_strips in supabase'}
    #get filena

    #gather assigned photostrip filename and all photo names to fetch from storage
    for response in photoQueryResponse.data:
        fileName = response['image_url']
        photoNames += response['raw_photos']

    #construct photo array with photos from storage
    for name in photoNames:
        try:
            photoRaw = (
                supabase.storage
                .from_(f'photos/raw/{eventName}')
                .download(name)
            )
        except:
            return {"code" : 400, "msg" : f'Failed to find valid photo under name {name} in event {eventName}'}
        #convert bytes into cv2 compatible photos
        nparr = np.frombuffer(photoRaw, np.uint8)
        photo = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        #add to photo array
        photos.append(photo)

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
        return {"code" : 400, "msg" : "Upload failure"}
    
    return {"code" : 200, "msg" : "Success"}
    

#HARD CODED VARIABLES FOR TESTING:
#print(stripConstruction(1, 1, "test"))