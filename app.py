from flask import Flask, request, jsonify, send_from_directory, send_file
import util
from strip_creation import stripConstruction, fetchTemplate
from flask_cors import CORS
import gphoto2 as gp
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

# Define a lock at the module level
global_template_lock = Lock()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
SAVE_DIRECTORY = os.path.expanduser("~/photobooth_flask_app")
global_template = None

# Global variables
camera = None
camera_lock = threading.Lock()
photo_in_progress = False
photo_lock = threading.Lock()

def set_camera_setting(setting_name, value):
    try:
        config = gp.check_result(gp.gp_camera_get_config(camera))
        setting = gp.check_result(gp.gp_widget_get_child_by_name(config, setting_name))
        
        # Only change if value is different
        current_value = setting.get_value()
        if str(current_value) != str(value):
            gp.check_result(gp.gp_widget_set_value(setting, value))
            gp.check_result(gp.gp_camera_set_config(camera, config))
            
    except gp.GPhoto2Error as e:
        print(f"⚠️  Setting '{setting_name}' failed: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error with '{setting_name}': {str(e)}")

def set_camera_preview_settings():
    print("Setting preview settings...")
    set_camera_setting('aperture', '3.5')
    set_camera_setting('iso', '4000')

def set_camera_photo_settings():
    print("Setting photo settings...")
    set_camera_setting('aperture', '8')
    set_camera_setting('iso', '320')

def set_live_view_mode():
    config = camera.get_config()
    settings_to_adjust = {
        'output': 'TFT',
        'evfmode': 1,
        'aperture': '3.5',
        'iso': '4000'
    }

    for setting_name, desired_value in settings_to_adjust.items():
        try:
            setting = config.get_child_by_name(setting_name)
            if setting:
                current_value = setting.get_value()
                print(f"Current {setting_name}: {current_value}")

                if str(current_value) != str(desired_value):
                    setting.set_value(desired_value)
                    print(f"Setting {setting_name} to {desired_value}")
                else:
                    print(f"{setting_name} is already set to desired value: {desired_value}")
            else:
                print(f"Setting {setting_name} not found")
        except gp.GPhoto2Error as e:
            print(f"Error setting {setting_name}: {str(e)}")

    try:
        camera.set_config(config)
        print("Applied new settings to camera")
        return True
    except gp.GPhoto2Error as e:
        print(f"Error applying settings: {str(e)}")
        return False

def initialize_camera():
    global camera
    try:
        print("\n🎥 Initializing camera...")
        os.system("sudo umount /dev/bus/usb/001/007")
        
        camera = gp.Camera()
        camera.init()
        
        # Pre-configure capture settings for speed
        config = camera.get_config()
        
        # Try to optimize capture settings
        try:
            # Set capture target to RAM
            capturetarget = config.get_child_by_name('capturetarget')
            if capturetarget:
                capturetarget.set_value('Internal RAM')
                camera.set_config(config)
            
            # Try to disable image review
            reviewtime = config.get_child_by_name('reviewtime')
            if reviewtime:
                reviewtime.set_value(0)
                camera.set_config(config)
                
            # Try to set fastest image quality
            imageformat = config.get_child_by_name('imageformat')
            if imageformat:
                imageformat.set_value('Large Fine JPEG')
                camera.set_config(config)
                
        except gp.GPhoto2Error:
            pass
            
        if set_live_view_mode():
            print("✅ Camera ready")
        else:
            print("⚠️  Live view setup failed")

    except gp.GPhoto2Error as error:
        print(f"❌ Camera initialization failed: {error}")
        camera = None

def take_photo():
    global photo_in_progress, camera

    with photo_lock:
        if photo_in_progress:
            return None
        photo_in_progress = True

    try:
        with camera_lock:
            if camera is None:
                initialize_camera()
            if camera is None:
                return None
            
            if not os.path.exists(SAVE_DIRECTORY):
                os.makedirs(SAVE_DIRECTORY)
            
            print('\n📸 Taking photo...')
            
            # Configure settings for photo
            settings_start = time.time()
            set_camera_photo_settings()
            settings_time = time.time() - settings_start
            
            # Capture with optimized settings
            capture_start = time.time()
            try:
                # Pre-configure capture target to RAM for faster transfer
                config = camera.get_config()
                capturetarget = config.get_child_by_name('capturetarget')
                if capturetarget:
                    capturetarget.set_value('Internal RAM')
                    camera.set_config(config)
                
                # Trigger capture
                trigger_time_start = time.time()
                file_path = camera.trigger_capture()
                trigger_time = time.time() - trigger_time_start
                
                # Wait for event
                wait_time_start = time.time()
                event_type, event_data = camera.wait_for_event(5000)
                wait_time = time.time() - wait_time_start
                
                # Get the file
                download_time_start = time.time()
                camera_file = camera.file_get(
                    file_path.folder, 
                    file_path.name, 
                    gp.GP_FILE_TYPE_NORMAL
                )
                
                timestamp = int(time.time())
                filename = f"photo_{timestamp}.jpg"
                full_path = os.path.join(SAVE_DIRECTORY, filename)
                camera_file.save(full_path)
                download_time = time.time() - download_time_start
                
            except gp.GPhoto2Error as error:
                print(f"❌ Capture error: {error}")
                return None
                
            total_time = time.time() - capture_start
            
            # Print timing summary
            print("\n⏱️  Timing Summary:")
            print(f"  Settings:  {settings_time:.2f}s")
            print(f"  Trigger:   {trigger_time:.2f}s")
            print(f"  Wait:      {wait_time:.2f}s")
            print(f"  Download:  {download_time:.2f}s")
            print(f"  Total:     {total_time:.2f}s\n")
            
            # Return to preview mode
            set_camera_preview_settings()
            
            return filename
    except Exception as error:
        print(f"❌ Error: {str(error)}")
        return None
    finally:
        with photo_lock:
            photo_in_progress = False

def reset_camera_connection():
    global camera
    print("Resetting camera connection...")
    
    with camera_lock:
        if camera:
            camera.exit()
            camera = None
        time.sleep(0.5)
        initialize_camera()
    print("Camera connection reset complete")

@app.route('/set-preview-settings')
def set_preview_settings_route():
    reset_camera_connection()
    return "Preview settings and live view enabled"

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
