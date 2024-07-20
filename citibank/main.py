import argparse
import logging
import os
import time
from base64 import urlsafe_b64encode
from email.message import EmailMessage
from glob import glob
from pathlib import Path

from citibank.browser.login import CitiAuthHandler
from citibank.gmail import Gmail
from citibank.settings import settings
from google.cloud import storage  # type: ignore

logger = logging.getLogger(__name__)


def main():
    """
    Entrypoint for Cloud Run function that logs into the Citibank
    web portal using Selenium, and downloads estatements
    """
    args: Arguments = parse_arguments()
    gmail_client = Gmail()
    download_directory = os.path.abspath(".")
    auth_handler = CitiAuthHandler(
        gmail_client=gmail_client, download_directory=download_directory
    )
    auth_handler.login()

    # wait for file to finish downloading
    time.sleep(3)

    # rename file
    file = glob(f"{download_directory}/*.pdf")[0]
    filepath = Path(file)
    dates = filepath.stem.split("_")[3]
    day = dates[0:2]
    month = dates[2:4]
    year = dates[4:8]
    identifier = filepath.stem.split("_")[2]
    pdf_filename = f"citbank-{identifier}-{year}-{month}-{day}{filepath.suffix}"
    try:
        os.rename(str(filepath), os.path.join(download_directory, pdf_filename))
    except FileNotFoundError:
        logger.info("Could not find file %s", str(filepath))

    # send file to bucket/email
    if args.upload:
        upload_to_cloud(source_filename=pdf_filename)

    if args.email:
        send_email(
            client=gmail_client,
            subject=f"Citibank eStatement - {Path(pdf_filename).stem.upper()}",
            attachment=pdf_filename,
        )


def upload_to_cloud(
    source_filename: str,
    bucket_name: str = settings.bucket_name,
    bucket_prefix: str = "citibank",
) -> None:
    client = storage.Client()
    bucket = client.get_bucket(bucket_name)
    blob_name = f"{bucket_prefix}/{source_filename}"
    blob = bucket.blob(blob_name)
    logger.info("Attempting to upload to 'gs://%s/%s'", bucket_name, bucket_name)
    blob.upload_from_filename(source_filename)
    logger.info("Uploaded to %s", blob_name)


def parse_arguments() -> argparse.Namespace:
    """
    Parse arguments for main entrypoint
    """
    parser = argparse.ArgumentParser(description="Download Citibank eStatement")
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Flag that determines whether to upload to a cloud bucket",
        default=True,
    )
    parser.add_argument(
        "--email",
        action="store_true",
        help="Flag that determines whether to send statement(s) to an email",
        default=True,
    )
    return parser.parse_args()


# pylint: disable=too-few-public-methods
class Arguments(argparse.Namespace):
    upload: bool
    email: bool


def send_email(
    client: Gmail,
    subject: str,
    attachment: str,
    to_address: str = settings.to_email,
    from_address: str = settings.from_email,
):
    message = EmailMessage()
    with open(attachment, "rb") as content_file:
        content = content_file.read()
        message.add_attachment(
            content, maintype="application", subtype="pdf", filename=attachment
        )
        message["To"] = to_address
        message["From"] = from_address
        message["Subject"] = subject
        encoded_message = urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {"raw": encoded_message}

        # send email
        (
            client.gmail_service.users()
            .messages()
            .send(userId="me", body=create_message)  # type: ignore
            .execute()
        )
        logger.info("Email sent: %s", message.__dict__)


if __name__ == "__main__":
    main()
