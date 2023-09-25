import os
import subprocess
import boto3
import configparser
from slacker import Slacker
import zipfile
import datetime


def log(text):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f'{timestamp} - {text}\n'
    log_filename = 'logs/DB_Export ' + datetime.datetime.now().strftime('%Y-%m-%d') + '.txt'
    with open(log_filename, 'a') as log_file:
        log_file.write(log_message)


def alert_slack(message):
    slack.chat.post_message(f'#{channel}', f"*{vp_name}*: {message}")


# Create database dump for each database schema
def create_db_dumps():
    try:
        for schema in all_schemas:
            dump_cmd = [
                dump_path,
                f"-h{db_host}",
                f"-u{db_user}",
                f"--password={db_password}",
                schema,
            ]
            with open(f"{schema}.sql", "w") as outfile:
                subprocess.run(dump_cmd, stdout=outfile, stderr=subprocess.PIPE, check=True)
                log(f'{schema}.sql created')

    except subprocess.CalledProcessError as e:
        log(f"Error creating database dump: {e}")
        alert_slack("Error creating database dump")
        exit(1)


# Create a ZIP file containing the dumps
def create_zip_file():
    with zipfile.ZipFile(f"{zip_file_name}.zip", 'w', zipfile.ZIP_DEFLATED) as zipf:
        for schema in all_schemas:
            zipf.write(f"{schema}.sql")
        log(f'{zip_file_name}.zip created')


def upload_file_to_s3(bucket_name, file_path, s3_key_name, aws_access_key, aws_secret_key):
    try:
        s3 = boto3.client('s3', aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
        s3.upload_file(file_path, bucket_name, s3_key_name)
        print("File uploaded successfully!")
        log(f"{s3_key_name} has been uploaded")
        alert_slack(f"{vp_name} - {zip_file_name} DB backup successful")
        return True
    except Exception as e:
        print(f"Error uploading file: {str(e)}")
        log(f"ERROR || {e}")
        alert_slack("Failed to upload export")
        return False


# Create a ConfigParser instance
config = configparser.ConfigParser()
config.read('config.ini')

# Access the values
dump_path = config.get('Dump', 'path')
vp_name = config.get('V-Portal', 'name')
channel = config.get('Slack', 'channel')
# AWS
aws_key: str = os.environ.get('backup-user-bot-aws_key')
aws_secret = os.environ.get('backup-user-bot-aws_secret')
bucket = config.get('AWS', 'bucket')
# MySQL
db_host = config.get('Database', 'db_host')
db_user = os.environ.get('DB-Username')
db_password = os.environ.get('DB-Password')
schemas = config.get('Database', 'schemas')
all_schemas = [schema for schema in schemas.split(',')]

zip_file_name = f"{vp_name}-db-dump-{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"

# Adding Slack
slack = Slacker('xoxb-161707178209-5299641378998-HY7MifoBB30tiKop4ZThWImL')

# Main function
create_db_dumps()
create_zip_file()
upload_file_to_s3(bucket, f"{zip_file_name}.zip", f"{vp_name}/{zip_file_name}.zip", aws_key, aws_secret)
try:
    os.remove(f"{zip_file_name}.zip")
    for schema in all_schemas:
        os.remove(f"{schema}.sql")
except Exception as e:
    log(f"ERROR || {e}")
