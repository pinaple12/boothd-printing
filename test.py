import gphoto2 as gp

def print_widget_details(widget):
    widget_type = gp.check_result(gp.gp_widget_get_type(widget))
    
    # Only attempt to get a value for widgets that support it
    if widget_type in [gp.GP_WIDGET_TEXT, gp.GP_WIDGET_RANGE, gp.GP_WIDGET_TOGGLE, gp.GP_WIDGET_RADIO, gp.GP_WIDGET_MENU, gp.GP_WIDGET_DATE]:
        try:
            value = gp.check_result(gp.gp_widget_get_value(widget))
        except gp.GPhoto2Error as e:
            value = "N/A (unable to retrieve value)"
    else:
        value = "N/A (unsupported widget type)"
    
    print(f"Widget Name: {gp.check_result(gp.gp_widget_get_name(widget))}")
    print(f"Widget Label: {gp.check_result(gp.gp_widget_get_label(widget))}")
    print(f"Widget Type: {widget_type}")
    print(f"Current Value: {value}")

    # Only print options for widgets that have them (like menus)
    if widget_type == gp.GP_WIDGET_MENU or widget_type == gp.GP_WIDGET_RADIO:
        count = gp.check_result(gp.gp_widget_count_choices(widget))
        if count > 0:
            print(f"  Available options:")
            for i in range(count):
                choice = gp.check_result(gp.gp_widget_get_choice(widget, i))
                print(f"    - {choice}")
    print()  # Blank line for better readability

def list_all_config(camera):
    # Get the camera configuration
    config = gp.check_result(gp.gp_camera_get_config(camera))

    # Iterate through the entire configuration tree
    def iterate_widgets(widget):
        print_widget_details(widget)
        count = gp.check_result(gp.gp_widget_count_children(widget))
        for idx in range(count):
            child_widget = gp.check_result(gp.gp_widget_get_child(widget, idx))
            iterate_widgets(child_widget)

    iterate_widgets(config)

# Initialize the camera
camera = gp.Camera()

try:
    # Start the camera session
    camera.init()
    
    # List all configuration options
    list_all_config(camera)

finally:
    # Clean up and exit
    camera.exit()
