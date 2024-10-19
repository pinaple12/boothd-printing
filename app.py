from flask import Flask, request, jsonify, send_from_directory, send_file
import util
from strip_creation import stripConstruction
from flask_cors import CORS
import gphoto2 as gp
import os
import threading
import time
from PIL import Image
import io
import cups
import tempfile

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
SAVE_DIRECTORY = os.path.expanduser("~/photobooth_flask_app")

# Global variables
camera = None
camera_lock = threading.Lock()
photo_in_progress = False
photo_lock = threading.Lock()

def set_live_view_mode():
    config = camera.get_config()

    settings_to_adjust = {
        'output': 'TFT',
        'evfmode': 1
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

#intiializes camera
def initialize_camera():
    global camera
    try:
        camera = gp.Camera()
        camera.init()
        print("Camera initialized successfully")

        if set_live_view_mode():
            print("Attempted to set clean live view mode")
        else:
            print("Failed to set clean live view mode. On-screen display might still be visible.")

    except gp.GPhoto2Error as error:
        print(f"Error initializing camera: {error}")
        camera = None

#focuses with camera
def autofocus():
    try:
        print("Attempting to autofocus...")
        config = camera.get_config()

        for section in config.get_children():
            for child in section.get_children():
                if 'autofocus' in child.get_name().lower():
                    child.set_value(1)
                    camera.set_config(config)
                    time.sleep(2)  # Give the camera time to focus
                    print(f"Autofocus triggered using {child.get_name()}")
                    return

        print("No specific autofocus setting found. Trying generic capture...")
        camera.capture(gp.GP_CAPTURE_PREVIEW)
        time.sleep(2)  # Give the camera time to adjust
        print("Generic autofocus completed")
    except gp.GPhoto2Error as error:
        print(f"Error during autofocus: {error}")

#takes photos
def take_photo_with_fallback():
    try:
        autofocus()
        return camera.capture(gp.GP_CAPTURE_IMAGE)
    except gp.GPhoto2Error as af_error:
        print(f"Autofocus error: {af_error}. Attempting manual focus capture.")
        try:
            config = camera.get_config()
            focus_mode = config.get_child_by_name('focusmode')
            if focus_mode:
                original_focus_mode = focus_mode.get_value()
                focus_mode.set_value('Manual')
                camera.set_config(config)
                file_path = camera.capture(gp.GP_CAPTURE_IMAGE)
                focus_mode.set_value(original_focus_mode)
                camera.set_config(config)
            else:
                file_path = camera.capture(gp.GP_CAPTURE_IMAGE)
            return file_path
        except gp.GPhoto2Error as manual_error:
            print(f"Manual focus capture also failed: {manual_error}")
            raise

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
            print('Taking a photo...')
            file_path = take_photo_with_fallback()

        full_path = os.path.join(SAVE_DIRECTORY, file_path.name)

        if not os.path.exists(SAVE_DIRECTORY):
            os.makedirs(SAVE_DIRECTORY)

        with camera_lock:
            camera_file = camera.file_get(file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL)
        camera_file.save(full_path)
        print(f'Photo saved as {full_path}')

        return file_path.name
    except gp.GPhoto2Error as error:
        print(f"Error taking photo: {error}")
        with camera_lock:
            camera = None  # Reset camera on error
        return None
    finally:
        with photo_lock:
            photo_in_progress = False

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

    if stripId is None or templateId is None or eventName is None:
        return "Missing one of stripId, templateId, or eventName", 400

    try:
        stripId = int(stripId)
        templateId = int(templateId)
    except ValueError:
        return "stripId and templateId must be integers", 400

    resp = stripConstruction(stripId, templateId, eventName)

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
    printer_name = "Dai_Nippon_Printing_DS-RX1"

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
        temp_filename = temp_file.name
        image_data.save(temp_filename, format="JPEG")

    options = {
        "media": paper_size,
        "fit-to-page": "True",
        "copies": str(copies)  # Convert copies to string for CUPS options
    }

    job_id = conn.printFile(printer_name, temp_filename, "Photobooth Print", options)

    return job_id

# Background task to handle strip construction and printing
def background_process(stripId, images, templateId, eventName, sessionId, copies, uuid):
    print(f"[INFO] Background process started for stripId: {stripId}")

    # Construct the photobooth strip
    print(f"[INFO] Constructing photobooth strip for event: {eventName}, session: {sessionId}")
    constructionResponse = stripConstruction(stripId, images, templateId, eventName, sessionId, uuid)

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


@app.route('/print_photobooth', methods=['POST'])
def print_photobooth():
    print("[INFO] Received request to print photobooth strip")

    # Receive the images
    images, error = util.process_uploaded_images(request)
    if error:
        print(f"[ERROR] Image processing failed: {error}")
        return jsonify({'error': error}), 400

    # Get photobooth ID from request
    photoBoothId = request.form.get('photoboothId')
    copies = request.form.get('copies')
    print(f"[INFO] Received photoboothId: {photoBoothId}")

    templateId, eventName, sessionId = util.findTemplate(photoBoothId)

    # Generate strip ID
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
    strip.save(img_io, 'JPEG', quality=70)
    img_io.seek(0)

    # Return the image file instead of printing
    return send_file(img_io, mimetype='image/jpeg')


def cleanup():
    global camera
    with camera_lock:
        if camera:
            camera.exit()
            camera = None

import atexit
atexit.register(cleanup)

# Initialize the camera when the app starts
with camera_lock:
    initialize_camera()

if __name__ == '__main__':
#     app.run(host='0.0.0.0')
    app.run(port=5001)
