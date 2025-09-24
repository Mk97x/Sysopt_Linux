import subprocess  # run commands on the computer
import os          
import glob        # search for files
from typing import List  

def list_systemd_enabled():
    """
    This function finds out which system services are turned on on the computer.
    System services are programs that run in the background, like a web server or SSH.
    """
    
    try:
        # subprocess.check_output executes a command and returns the result
        # systemctl list-unit-files --type=service --state=enabled
        # This is a command that you would normally type in the command line
        # It lists all services that are turned on (enabled)
        command = ["systemctl", "list-unit-files", "--type=service", "--state=enabled"]
        output = subprocess.check_output(command, text=True)
        
        # The output looks like this:
        # ssh.service                     enabled
        # docker.service                  enabled
        # apache2.service                 enabled
        # ...
        
        lines = output.splitlines()
        services = []
        
        for line in lines:
            if ".service" in line:
                words = line.split()
                if len(words) > 0:  
                    services.append(words[0])

        return services
        
    except Exception as e:
        # If anything goes wrong (e.g. the command doesn't work), 
        # we return an empty list
        return [f"Error: {e}"]

def list_user_autostart():
    """
    This function finds programs that automatically start when the user logs in.
    These are programs that are in a special folder: ~/.config/autostart
    """
    
    autostart_folder = os.path.expanduser("~/.config/autostart")

    desktop_files = glob.glob(os.path.join(autostart_folder, "*.desktop"))
    
    autostart_programs = []
    
    for file in desktop_files:
        filename = os.path.basename(file) # only file name no .ending
        autostart_programs.append(filename)
    
    return autostart_programs

if __name__ == "__main__":
    print("System services that are turned on:")
    systemd_services = list_systemd_enabled()
    if len(systemd_services) > 5:
        print(systemd_services[:5])  # Only the first 5 elements
    else:
        print(systemd_services)
    
    print("Programs that start automatically:")
    autostart_programs = list_user_autostart()
    print(autostart_programs)

    print("\nExplanation:")
    print("- System services run in the background for the whole system")
    print("- Autostart programs start when you log in to your computer")