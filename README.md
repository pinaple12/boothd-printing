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

## API:

