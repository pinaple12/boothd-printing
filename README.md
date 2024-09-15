# boothd-printing #
Python flask server, hosting boothd operations

##Data Flow 

Data flow is described by the following photo:
![Data Flow](https://github.com/user-attachments/assets/ad45e416-190c-4a18-a646-15a4cdce5db3)

## Data Model ##

All data is stored using Supabase. 

### TABLES: ###

Tables can be seen with the schema visualizer below:
<img width="1166" alt="Screenshot 2024-09-14 at 8 36 50 PM" src="https://github.com/user-attachments/assets/7ffefa7f-fa6a-4b76-a2fb-8a6011f7c5cd">

### STORAGE BUCKETS: ###
Photos and templates themselves are stored in the following buckets:

Photos
- /raw
Raw photos are uploaded to the raw folder, organized in subfolders labeled by event name
- /photostrips
Photo strips are uploaded to the photostrips folder, organized in subfolders labeled by event name

Templates
All templates are stored here as png files

## API

## Table of Contents
1. [Installation](#installation)
2. [Usage](#usage)
3. [API Endpoints](#api-endpoints)
4. [File Structure](#file-structure)
5. [Dependencies](#dependencies)

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/pinaple12/boothd-printing/
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up your Supabase credentials in `strip_creation.py`:
   ```python
   url: str = 'https://fxpfrvfpgjqyermtbtwu.supabase.co'
   key: str = 'YOUR-SECRET-KEY'
   ```

## Usage

Run the Flask application:

```
python app.py
```

The server will start, and you can access the API endpoints.

## API Endpoints

### 1. Create Strip

- **URL:** `/createStrip`
- **Method:** POST
- **Description:** Constructs a photo strip and uploads it to Supabase.
- **Parameters:**
  - `stripId` (string): ID of the strip
  - `templateId` (string): ID of the template
  - `eventName` (string): Name of the event being served
- **Response:** 
  - Success: 200 OK with a success message
  - Error: 400 Bad Request or 500 Internal Server Error with an error message

## File Structure

- `app.py`: Main Flask application file
- `strip_creation.py`: Contains the `stripConstruction` function for creating and uploading photo strips
- `util.py`: Utility functions for image processing

## Dependencies

- Flask
- Supabase Python Client
- OpenCV (cv2)
- NumPy

Make sure to install these dependencies using the `requirements.txt` file.

## Note

Ensure that you have the necessary permissions and access to the Supabase project. Replace the `SECRET-KEY` in `strip_creation.py` with your actual Supabase key before running the application.


