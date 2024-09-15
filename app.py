from flask import Flask, request
from strip_creation import stripConstruction

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

'''
stripId - string representation of strip id
templateId - string representation of template name
eventName - name of event being served

This route constructs a photostrip and uploads it to the supabase with a given stripId, templateId, and eventName
'''
@app.post("/createStrip")
def stripCreation():
    stripId = request.form.get('stripId')
    templateId = request.form.get('templateId')
    eventName = request.form.get('eventName')

    #make sure all 3 were supplied
    if stripId is None or templateId is None or eventName is None:
        return "Missing one of stripId, templateId, or eventName", 400
    
    #try converting stripId and templateId into integers
    try:
        stripId = int(stripId)
        templateId = int(templateId)
    except ValueError:
        return "stripId and templateId must be integers", 400

    #constructs the strip
    resp = stripConstruction(stripId, templateId, eventName)

    #make sure we received a valid response
    if 'msg' not in resp or 'code' not in resp:
        return "Internal error: Invalid response from stripConstruction", 500

    return resp["msg"], resp['code']

    

    
    

    