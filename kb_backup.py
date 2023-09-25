import os
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import datetime
from bs4 import BeautifulSoup
import json
from slacker import Slacker
import configparser
import boto3
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager


def log(text):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f'{timestamp} - {text}\n'
    log_filename = 'logs/KB_Export ' + datetime.datetime.now().strftime('%Y-%m-%d') + '.txt'
    with open(log_filename, 'a') as log_file:
        log_file.write(log_message)


def alert_slack(message):
    slack.chat.post_message(f'#{channel}', f"*{vp_name}*: {message}")


def check_loading():
    try:
        loading_flag = True
        is_object_loaded = True
        loop_count = 0
        while loading_flag or is_object_loaded:
            loop_count = loop_count + 1
            if loop_count >= 50:
                break
            loading_flag = driver.execute_script("return loadActiveTabFlag;")
            is_object_loaded = driver.execute_script("return isObjectLoaded;")
            if loading_flag is None:
                loading_flag = True
            if is_object_loaded is None:
                is_object_loaded = True
            time.sleep(5)
    except Exception as e:
        log(f'ERROR || {e}')


def login():
    current_url = driver.current_url 
    if "/vportal/login.html" not in current_url:
        driver.get(url)
        driver.implicitly_wait(60)
    # Login to V-Portal
    username = driver.find_element(By.ID, 'username')
    username.send_keys(os.environ.get('VP-Username'))
    password = driver.find_element(By.ID, 'password')
    password.send_keys(os.environ.get('VP-Password'))
    password.send_keys(Keys.RETURN)
    WebDriverWait(driver, 30).until(
        EC.invisibility_of_element_located((By.CLASS_NAME, "loading.ui-state-default.ui-state-active"))
    )
    time.sleep(5)
    log(f'V-Portal Login Successful')


def login_open_project(p):
    # Login to V-Portal
    login()

    # Open Project
    current_url = driver.current_url 
    if "/vportal/viewProjectList.html" in current_url or "/vportal/loginSuccess.html" in current_url:
        try:
            js_code = f"openProjectDB('#gridProjectList',{p})"
            driver.execute_script(js_code)
            check_loading()
            log(f'Project: {p} || Project Opened')
        except:
            log(f"ERROR || Project {p} not found ")
            pass

    driver.implicitly_wait(60)


def logout():
    # Logout
    driver.execute_script("window.location.href = '/vportal/logout.html?myAuthTypeScript=OWN'")
    driver.implicitly_wait(60)
    log(f'Logged out Successful')


def get_project_details():
    try:
        # Login to V-Portal
        login()

        # Get all project details
        driver.execute_script(f"window.location.href = '/vportal/getAllProjects.html?'")
        driver.implicitly_wait(60)
        project_response = json.loads(str(BeautifulSoup(driver.page_source, 'html.parser').body.text))
        log("Got the project details")

        logout()

        return project_response["rows"]
    except Exception as e:
        log(f"ERROR || {e}")
        alert_slack(f"Error getting project details")


def get_project_name(p):
    project_name = None
    for project in project_details:
        if project['projectId'] == p:
            project_name = project['projectName']
            break
    return project_name


def get_export_status(p):
    # Check the export status
    driver.execute_script(f"window.location.href = '/vportal/isKBExportProcessed.html?uniqueTabId=contents2'")

    # Set timeout for 20 minutes from now
    timeout = time.time() + 60 * 20

    # Waits until the export has been successful or 20min
    while True:
        driver.implicitly_wait(60)
        export_status_response = driver.page_source
        export_status = BeautifulSoup(export_status_response, 'html.parser').body.text

        if export_status == "Success":
            log(f"Project: {p} || Export file generated")
            break
        elif time.time() > timeout:
            log(f"ERROR || Timeout 1hr exceeded when getting the data ")
            break
        elif "An error has occurred OR your session has been invalidated due to login on other browser/system." in export_status:
            log(f"ERROR || Session has been invalidated ")
            break
        else:
            log(f"Project: {p} || Export still in progress... || {export_status}")
            time.sleep(5)
            driver.refresh()


def get_export_id(p, export_file):
    try:
        # Login and Open Project
        login_open_project(p)

        # Get the KB Export list
        driver.execute_script(f"window.location.href = '/vportal/getAllKbExportList.html?'")
        driver.implicitly_wait(60)
        export_list_response = driver.page_source
        export_list = json.loads(str(BeautifulSoup(export_list_response, 'html.parser').body.text))
        rows = export_list["rows"]

        kb_export_id = None
        for row in rows:
            if row["fileNm"] == f"{export_file}.xml":
                kb_export_id = row["kbExportId"]
                break
            else:
                log(f"ERROR || Export file '{export_file}.xml' not found")

        log(f'Project: {p} || Export ID Retrieved: {kb_export_id}')

        # Logout
        logout()

        return kb_export_id

    except Exception as e:
        log(f"ERROR || {e}")


def download_wait(p, path):
    # Set Timeout to 5 min
    timeout = time.time() + 60 * 5
    wait = True

    # check if the file is still downloading
    while wait and time.time() < timeout:
        time.sleep(2)
        wait = False
        log(f'Project: {p} || File is still downloading...')
        for file in os.listdir(path):
            if file.endswith('.crdownload'):
                log(f'Project: {p} || Download completed')
                wait = True


def create_export(p, export_file):
    try:
        # Login and Open Project
        login_open_project(p)
        
        # Go to Export summary tab
        js_code = "javascript:openTab('KB Export Summary',null,'kbExportSummary.html',true)"
        driver.execute_script(js_code)
        check_loading()
        log(f'Project: {p} || Export summary opened')

        # Create new export
        js_code = "javascript:openTab('KB Export Detail',null,'kbExportMgmt.html?kbnm=RECOGNITION',true)"
        driver.execute_script(js_code)
        time.sleep(10)
        check_loading()
        log(f"Project: {p} || New Export Opened")

        # Select all content
        js_code = "openAttribute('leftSelAll')"
        driver.execute_script(js_code)
        check_loading()
        log(f"Project: {p} || Select answers")
        
        # Set Export file name
        input_field = driver.find_element(By.ID, 'kbExportFileNameId')
        input_field.clear()
        input_field.send_keys(export_file)
        log(f"Project: {p} || File name set to: {export_file}")

        # Skip the Check
        js_code = "saveKbExport(true)"
        driver.execute_script(js_code)
        check_loading()
        log(f"Project: {p} || Export has been saved")

        # Check if the Export has been completed
        get_export_status(p)

        # Logout
        logout()

        alert_slack(f"{get_project_name(p)} - {export_file}.xml has been Generated")
    except Exception as e:
        log(f"ERROR || {e}")
        alert_slack("Failed to generate export")


def download_export(p, export_file):
    try:
        # Getting the Export ID of the created file
        export_id = get_export_id(p, export_file)

        # Login and Open Project
        login_open_project(p)

        # Go to Export summary tab
        js_code = "javascript:openTab('KB Export Summary',null,'kbExportSummary.html',true)"
        driver.execute_script(js_code)
        check_loading()
        log(f'Project: {p} || Export summary opened')

        wait = WebDriverWait(driver, 10)
        wait.until(EC.invisibility_of_element_located((By.ID, 'load_kbExportSummary')))

        # Download the export file.
        js_code = f"downloadKbExport('#kbExportSummary',{export_id});"
        driver.execute_script(js_code)
        check_loading()
        log(f'Project: {p} || Download export file triggerd')

        # Waits for download to finish
        download_wait(p, download_path)

        if os.path.isfile(f'{download_path}/{export_file}.xml'):
            log(f'Project: {p} || Download file can be found')
        else:
            log(f'ERROR || Download file not found')

        # Logout
        logout()

        alert_slack(f"{get_project_name(p)} - {export_file}.xml has been Downloaded")
    except Exception as e:
        log(f"ERROR || {e}")
        alert_slack("Failed to download export")


def upload_file_to_s3(p, bucket_name, file_path, s3_key_name, aws_access_key, aws_secret_key):
    try:
        s3 = boto3.client('s3', aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
        s3.upload_file(file_path, bucket_name, s3_key_name)
        log(f"Project: {p} || {s3_key_name} has been uploaded")
        alert_slack(f"{get_project_name(p)} - {s3_key_name} has been Uploaded")
        return True
    except Exception as e:
        print(f"Error uploading file: {str(e)}")
        log(f"ERROR || {e}")
        alert_slack("Failed to upload export")
        return False


def create_download_upload():
    for project in all_projects:
        # Export file name
        export_file_name = f"{get_project_name(project)}_kb_dump-{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
        log(f"Project: {project} || Export file name: {export_file_name}")
        # Create an export file
        create_export(project, export_file_name)
        # Download the export file
        download_export(project, export_file_name)
        # Upload to S3 Bucket
        upload_file_to_s3(project, bucket, f"{export_file_name}.xml",
                          f"{get_project_name(project)}/{export_file_name}.xml", aws_key, aws_secret)
        # Delete the file
        os.remove(f"{export_file_name}.xml")


# Create a ConfigParser instance
config = configparser.ConfigParser()

# Read the config file
config.read('config.ini')

# Access the values
download_path = config.get('Download', 'path')
url = config.get('V-Portal', 'url')
vp_name = config.get('V-Portal', 'name')
projects_list = config.get('Projects', 'projects')
all_projects = [int(project) for project in projects_list.split(',')]
channel = config.get('Slack', 'channel')
aws_key: str = os.environ.get('backup-user-bot-aws_key')
aws_secret = os.environ.get('backup-user-bot-aws_secret')
bucket = config.get('AWS', 'bucket')


# Adding Slack
slack = Slacker('xoxb-161707178209-5299641378998-HY7MifoBB30tiKop4ZThWImL')

# Configure Chrome options
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Set preferences to specify the download directory
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": download_path,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})

# Specify option path for webdriver
driver = webdriver.Chrome(options=chrome_options, service=ChromeService(ChromeDriverManager().install()))

# navigate to the website
driver.get(url)
driver.implicitly_wait(60)

# Get Project Details
project_details = get_project_details()
# print(project_details)

# Create, Download and Upload KB Export
create_download_upload()

# close the browser
driver.quit()
