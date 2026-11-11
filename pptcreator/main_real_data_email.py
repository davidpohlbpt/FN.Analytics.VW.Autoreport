import os

from pptcreator.creator.send_email.send_email import send_email


def main() -> None:

    config_dict = {
        "target_file_name": "Test_PPT",
        "target_blob_container": "ppt_creator",
        "filter_column": "project_name",
        "recipients": ["maximilian.herz@bearingpoint.com"],
        "menu_item_id": 704,
        "report_id": 704,
    }

    config_dict = send_email(config_dict)


if __name__ == "__main__":
    main()
