import cv2
import numpy as np
from supabase import create_client, Client
url: str = 'https://fxpfrvfpgjqyermtbtwu.supabase.co'
key: str = 'SECRET-KEY'
supabase: Client = create_client(url, key)

'''
template - cv2 image object containing photo strip template
imgs - array of cv2 image objects containing photos that were taken
positions - array of int tuples containing (x-coordinate, y-coordinate) of each image
photoWidth - integer describing x dimension of photos
photoHeight - integer describing y dimension of photos

This function creates a photostrip, and returns it as a cv2 object
'''
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