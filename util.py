import cv2
import numpy as np
import uuid as uuid_module
from supabase import create_client, Client

from dotenv import load_dotenv
import os

load_dotenv('.env.local')

url: str = 'https://fxpfrvfpgjqyermtbtwu.supabase.co'
key: str = os.getenv('KEY')
supabase: Client = create_client(url, key)

'''
template - cv2 image object containing photo strip template
imgs - array of cv2 image objects containing photos that were taken
positions - array of int tuples containing (x-coordinate, y-coordinate) of each image
photoWidth - integer describing x dimension of photos
photoHeight - integer describing y dimension of photos

This function creates a photostrip, and returns it as a cv2 object
'''

#returns templateId and event name of the latest event the given photobooth id was active at
def findTemplate(photoBoothId):
    templateQueryResponse = (
        supabase.table('photoshoot_sessions')
        .select('template_id, event_name', 'id')
        .eq('photobooth_id', photoBoothId)
        .order('session_time', desc=True)
        .limit(1)
        .execute()
    ).data[0]

    return templateQueryResponse['template_id'], templateQueryResponse['event_name'], templateQueryResponse['id']

def generateStripId(sessionId):
    idQueryResponse = (
        supabase.table('photo_strips')
        .select('id')
        .order('id', desc=True)
        .limit(1)
        .execute()
    ).data[0]
    id = idQueryResponse['id'] + 1
    uuid = generateUuid(id, sessionId)

    return id, uuid

def generateUuid(id, sessionId):
    uuid = str(uuid_module.uuid4())
    # create empty strip row with id and uuid
    supabase.table('photo_strips').insert({'id': id, 'uuid': uuid, 'image_url': 'dummy', 'session_id': sessionId, 'raw_photos': []}).execute()
    return uuid

def process_uploaded_images(request):
    images = []
    for i in range(3):
        image_file = request.files.get(f'image{i+1}')
        if image_file:
            try:
                # Convert the file into a NumPy array and then into a cv2 image
                file_bytes = np.frombuffer(image_file.read(), np.uint8)
                img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                if img is None:
                    return None, f'Error processing image {i+1}'
                images.append(img)
            except Exception as e:
                return None, f'Error processing image {i+1}: {str(e)}'
        else:
            return None, f'Image {i+1} is missing'

    if len(images) != 3:
        return None, 'Exactly 3 images are required'

    return images, None

def create_strip(template, imgs, positions, photoWidth, photoHeight):
    #HARD CODED: aspect of dslr being used
    aspect_ratio = 3/2

    target_ratio = photoWidth / photoHeight

    for i, img in enumerate(imgs):
        # image is too wide, resize based on height and crop width
        if aspect_ratio > target_ratio:
            new_height = photoHeight
            new_width = int(new_height * aspect_ratio)
            resized_img = cv2.resize(img, (new_width, new_height))

            crop_start_x = (new_width - photoWidth) // 2
            cropped_img = resized_img[:, crop_start_x:crop_start_x + photoWidth]
        # image is too tall, resize based on width and crop height
        elif aspect_ratio < target_ratio:
            new_width = photoWidth
            new_height = int(new_width / aspect_ratio)
            resized_img = cv2.resize(img, (new_width, new_height))

            crop_start_y = (new_height - photoHeight) // 2
            cropped_img = resized_img[crop_start_y:crop_start_y + photoHeight, :]
        #just resize the image
        else:
            cropped_img = cv2.resize(img, (photoWidth, photoHeight))

        pos = positions[i]
        template[pos[1]:pos[1] + photoHeight, pos[0]:pos[0] + photoWidth] = cropped_img

    return template


#testing function
def generate_white_blocks():
    images = []
    width = 300  # Example width
    height = int(width * 2 / 3)  # Aspect ratio 3:2

    for _ in range(3):
        # Create a white block with the specified width and height
        white_block = np.ones((height, width, 3), dtype=np.uint8) * 255  # 3-channel white image (RGB)
        images.append(white_block)

    return images
