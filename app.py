from flask import Flask, request, jsonify, send_from_directory, send_file
import util
from strip_creation import stripConstruction, fetchTemplate
from flask_cors import CORS
import os
import threading
import time
from PIL import Image
import io
import cups
import tempfile
import cv2
import numpy as np
from threading import Lock
import subprocess
import json

# Define a lock at the module level
global_template_lock = Lock()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
SAVE_DIRECTORY = os.path.expanduser("~/photobooth_flask_app")
global_template = None

# Global variables
camera_lock = threading.Lock()
photo_in_progress = False
photo_lock = threading.Lock()

def run_gphoto_command(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error running command: {command}")
            print(f"Error output: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"Exception running command: {str(e)}")
        return False

def set_camera_setting(setting_name, value):
    command = f"gphoto2 --set-config {setting_name}={value}"
    return run_gphoto_command(command)
    
def set_preview_settings():
    """Configure camera for bright preview mode"""
    try:
        command = (
            "gphoto2 "
            "--set-config aperture=3.5 "
            "--set-config iso=4000"
        )
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error setting preview mode: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"Error in preview settings: {str(e)}")
        return False

def set_photo_settings():
    """Configure camera for flash photo mode"""
    try:
        command = (
            "gphoto2 "
            "--set-config aperture=8 "
            "--set-config iso=320"
        )
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error setting photo mode: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"Error in photo settings: {str(e)}")
        return False

def enable_live_view():
    """Enable camera's live view mode"""
    try:
        command = (
            "gphoto2 "
            "--set-config output=TFT "
            "--set-config evfmode=1"
        )
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error enabling live view: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"Error in live view: {str(e)}")
        return False

def initialize_camera():
    print("Initializing camera...")
    try:
        # Reset USB first
        os.system("sudo umount /dev/bus/usb/001/007")
        
        # Test camera connection
        result = subprocess.run("gphoto2 --auto-detect", shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print("Failed to detect camera")
            return False

        # Enable live view and set initial preview settings
        if not enable_live_view():
            print("Failed to enable live view")
            return False
            
        if not set_preview_settings():
            print("Failed to set preview settings")
            return False
            
        print("Camera initialized successfully with live view")
        return True
    except Exception as e:
        print(f"Error initializing camera: {str(e)}")
        return False

def take_photo():
    global photo_in_progress

    with photo_lock:
        if photo_in_progress:
            return None
        photo_in_progress = True

    try:
        with camera_lock:
            if not os.path.exists(SAVE_DIRECTORY):
                os.makedirs(SAVE_DIRECTORY)
                
            timestamp = int(time.time())
            filename = f"photo_{timestamp}.jpg"
            full_path = os.path.join(SAVE_DIRECTORY, filename)
            
            print('Taking a photo...')
            
            # Configure for photo
            settings_start = time.time()
            set_photo_settings()
            settings_end = time.time()
            print(f"Photo settings configuration time: {settings_end - settings_start:.2f} seconds")
            
            # Take the photo
            capture_start = time.time()
            command = (
                f"gphoto2 --capture-image-and-download "
                f"--force-overwrite "
                f"--filename={full_path}"
            )
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Error taking photo: {result.stderr}")
                return None
                
            capture_end = time.time()
            print(f"Capture time: {capture_end - capture_start:.2f} seconds")
            
            # Return to preview mode
            set_preview_settings()
            
            return filename
    except Exception as error:
        print(f"Error taking photo: {str(error)}")
        return None
    finally:
        with photo_lock:
            photo_in_progress = False

def reset_camera_connection():
    print("Resetting camera connection...")
    # Quick reset instead of full process kill
    subprocess.run("gphoto2 --reset", shell=True)
    time.sleep(0.5)  # Reduced wait time
    return initialize_camera()

@app.route('/set-preview-settings')
def set_preview_settings_route():
    if set_preview_settings():
        return "Preview settings applied successfully"
    return "Failed to apply preview settings", 500

@app.route('/')
def home():
    if photo_in_progress:
        return jsonify({'error': 'Photo already in progress. Please wait.'}), 429
    photo_filename = take_photo()

    if photo_filename is None:
        return jsonify({'error': 'Failed to take photo. Please try again later.'}), 503
    response = send_from_directory(SAVE_DIRECTORY, photo_filename)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    #set_camera_preview_settings()
    # Convert response data to bytes and create a higher quality JPEG
    img_io = io.BytesIO()
    with Image.open(os.path.join(SAVE_DIRECTORY, photo_filename)) as img:
        img.save(img_io, format='JPEG', quality=95)
    img_io.seek(0)
    
    # Create new response with the compressed JPEG
    response = send_file(img_io, mimetype='image/jpeg')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/test')
def test():
    return "hey this is a test"


@app.post("/createStrip")
def stripCreation():
    #if not provided, they should be from request object in route
    stripId = request.form.get('stripId')
    templateId = request.form.get('templateId')
    eventName = request.form.get('eventName')
    #send in an array
    photos = request.form.get("photos")

    if stripId is None or templateId is None or eventName is None:
        return "Missing one of stripId, templateId, or eventName", 400

    try:
        stripId = int(stripId)
        templateId = int(templateId)
    except ValueError:
        return "stripId and templateId must be integers", 400
    
        #if this is the first load, save it in
    if global_template is None:
        resp = fetchTemplate(templateId)
        if resp["code"] != 200:
            return "Error in template retrieval from supabase", 400
        else:
            global_template = resp["data"]


    resp = stripConstruction(stripId, global_template, eventName)

    if 'msg' not in resp or 'code' not in resp:
        return "Internal error: Invalid response from stripConstruction", 500

    return resp["msg"], resp['code']

def create_photobooth_strip(images):
    full_width = 4 * 300
    full_height = 6 * 300
    strip_width = 2 * 300
    strip_height = full_height
    single_image_height = strip_height // 3

    full_image = Image.new('RGB', (full_width, full_height), color='white')

    for strip_index in range(2):
        strip = Image.new('RGB', (strip_width, strip_height), color='white')

        for i, img in enumerate(images):
            img_ratio = img.width / img.height
            strip_ratio = strip_width / single_image_height

            if img_ratio > strip_ratio:
                new_height = single_image_height
                new_width = int(new_height * img_ratio)
            else:
                new_width = strip_width
                new_height = int(new_width / img_ratio)

            img_resized = img.resize((new_width, new_height), Image.LANCZOS)

            left = (new_width - strip_width) // 2
            top = (new_height - single_image_height) // 2
            right = left + strip_width
            bottom = top + single_image_height
            img_cropped = img_resized.crop((left, top, right, bottom))

            strip.paste(img_cropped, (0, i * single_image_height))

        full_image.paste(strip, (strip_index * strip_width, 0))

    return full_image

def print_image(image_data, paper_size, copies=1):
    conn = cups.Connection()
    printer_name = "My_DSRX1_Printer"

    # Set exact 4x6 dimensions based on 2x6 original image
    new_width = int(image_data.width * 2)  # Ensure it's double-width
    new_height = int(image_data.height)    # Keep same height

    # Create new 4x6 canvas and paste images with integer-based positions
    new_image = Image.new('RGB', (new_width, new_height), (255, 255, 255))
    new_image.paste(image_data, (0, 0))                    # Left side
    new_image.paste(image_data, (image_data.width, 0))     # Right side

    # Save the new 4x6 image to a temporary file
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
        temp_filename = temp_file.name
        new_image.save(temp_filename, format="JPEG")

    # Set the print options
    options = {
        "media": paper_size,
        "fit-to-page": "True",
        "copies": str(copies)  # Convert copies to string for CUPS options
    }

    # Print the file
    job_id = conn.printFile(printer_name, temp_filename, "Photobooth Print", options)

    return job_id


# Background task to handle strip construction and printing
def background_process(stripId, images, templateId, eventName, sessionId, copies, uuid):
    print(f"[INFO] Background process started for stripId: {stripId}")

    # Construct the photobooth strip
    print(f"[INFO] Constructing photobooth strip for event: {eventName}, session: {sessionId}")
    constructionResponse = stripConstruction(stripId, images, templateId, global_template, eventName, sessionId, uuid)

    if constructionResponse["code"] == 400:
        print(f"[ERROR] Strip construction failed: {constructionResponse['msg']}")
        return

    # Turn encoded image into a PIL Image
    print(f"[INFO] Converting constructed strip to image for stripId: {stripId}")
    stripBytes = constructionResponse["data"].tobytes()
    stripBuffer = io.BytesIO(stripBytes)
    strip = Image.open(stripBuffer)

    try:
        # Submit the print job
        print(f"[INFO] Sending strip to print for stripId: {stripId}")
        job_id = print_image(strip, "2x6*2", copies)
        print(f"[SUCCESS] Print job submitted with job_id: {job_id}")
    except Exception as e:
        print(f"[ERROR] Printing failed for stripId: {stripId} - {str(e)}")


from threading import Lock

# Define a lock at the module level
global_template_lock = Lock()

@app.route('/print_photobooth', methods=['POST'])
def print_photobooth():
    print("[INFO] Received request to print photobooth strip")

    # Initialize response in case of early errors
    response = jsonify({'error': 'Unexpected error occurred'}), 500

    # Process uploaded images
    images, error = util.process_uploaded_images(request)
    if error:
        print(f"[ERROR] Image processing failed: {error}")
        return jsonify({'error': error}), 400

    # Retrieve photobooth ID and copies
    photoBoothId = request.form.get('photoboothId')
    copies = request.form.get('copies', 1)
    print(f"[INFO] Received photoboothId: {photoBoothId}")

    # Fetch template information
    templateId, eventName, sessionId = util.findTemplate(photoBoothId)
    
    # Check and assign global_template with a lock
    global global_template
    with global_template_lock:
        if global_template is None:
            resp = fetchTemplate(templateId)
            if resp["code"] != 200:
                print(f"[ERROR] Template retrieval failed: {resp['msg']}")
                return jsonify({'error': "Error in template retrieval from Supabase"}), 400
            global_template = resp["data"]

    print(f"[INFO] Global template is none?: {global_template is None}")
    
    # Generate strip ID and UUID
    stripId, uuid = util.generateStripId(sessionId)
    print(f"[INFO] Generated stripId: {stripId} and UUID: {uuid}")

    # Send strip ID back immediately to the client
    response = jsonify({'message': 'Strip ID generated, processing continues in background', 'uuid': uuid})
    response.status_code = 202

    # Start the background process for constructing and printing the strip
    print(f"[INFO] Starting background process for stripId: {stripId}")
    thread = threading.Thread(target=background_process, args=(stripId, images, templateId, eventName, sessionId, copies, uuid))
    thread.start()

    # Return the response with strip ID right away
    print(f"[INFO] Response sent with stripId: {stripId}")
    return response

@app.route('/test_photobooth_strip', methods=['POST'])
def test_photobooth_strip():
    print("received photobooth strip test")
    images, error = util.process_uploaded_images(request)  # Use the same util function for processing
    if error:
        return jsonify({'error': error}), 400

    # Generate the photobooth strip
    photoBoothId = request.form.get('photoboothId')
    templateId, eventName, sessionId = util.findTemplate(photoBoothId)
    stripId = util.generateStripId()

    constructionResponse = stripConstruction(stripId, images, templateId, eventName, sessionId)

    if constructionResponse["code"] == 400:
        return jsonify({'error': f'Strip construction failed: {constructionResponse["msg"]}'}), 500

    # Turn encoded image into a PIL Image
    stripBytes = constructionResponse["data"].tobytes()
    stripBuffer = io.BytesIO(stripBytes)
    strip = Image.open(stripBuffer)

    # Save image into BytesIO to send as a response
    img_io = io.BytesIO()
    strip.save(img_io, 'JPEG', quality=95)
    img_io.seek(0)

    # Return the image file instead of printing
    return send_file(img_io, mimetype='image/jpeg')


def cleanup():
    print("Cleaning up camera connection...")
    os.system("pkill -f gphoto2")

import atexit
atexit.register(cleanup)

# Initialize the camera when the app starts
with camera_lock:
    initialize_camera()

if __name__ == '__main__':
    app.run(host='0.0.0.0')
