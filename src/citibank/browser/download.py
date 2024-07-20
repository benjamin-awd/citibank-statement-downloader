import json
import logging
from datetime import datetime
from functools import cached_property
from typing import Optional
from uuid import uuid4

import requests
from dateutil.parser import parse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

logger = logging.getLogger(__name__)


class StatementRecord(BaseModel):
    """
    Serializes a JSON object with estatement metadata
    {
        'statementDate': '2023-12-31',
        'statementType': 'DBSSPA',
        'statementHashKey': '...',
        'description': 'DBS Savings Plus Account',
        'entityName': [],
        'address': [],
        'productCode': '...',
        'productReferenceNo': '...',
        'currency': None,
        'formattedAccountNumber': '...'}
    }
    into a Pydantic model, with keys converted to snake case
    """

    model_config = ConfigDict(alias_generator=to_camel)

    statement_date: str
    statement_type: str
    statement_hash_key: str
    description: str
    entity_name: list
    address: list
    product_code: str
    product_reference_no: str
    currency: Optional[str]
    formatted_account_number: str


class StatementDownloader:
    def __init__(self, cookies: dict, user_agent: str):
        self.user_agent = user_agent
        self.cookies = cookies
        self.ibanking_home_url: str = "https://internet-banking.dbs.com.sg"
        self.download_endpoint: str = (
            self.ibanking_home_url + "/api/v3/channels/estatements/inquiry"
        )
        self.list_endpoint: str = (
            self.ibanking_home_url + "/api/v3/channels/estatements"
        )

    @staticmethod
    def create_utc_timestamp() -> str:
        current_datetime = datetime.utcnow()
        timestamp = current_datetime.strftime("%Y-%m-%d %H:%M:%S")

        return timestamp

    @cached_property
    def extracted_cookies(self) -> dict:
        desired_cookie_names = ["X-dbs-cust-sysgen-id", "X-dbs-session-token"]
        extracted_cookies = {}

        for cookie in self.cookies:
            for name in desired_cookie_names:
                if cookie["name"] == name:
                    extracted_cookies[name] = cookie["value"]

        if set(extracted_cookies.keys()) != set(desired_cookie_names):
            raise RuntimeError(
                f"Missing cookies: extracted cookies {set(extracted_cookies.keys())} "
                f"!= {set(desired_cookie_names)}"
            )

        return extracted_cookies

    @cached_property
    def dbs_session_token(self) -> str:
        return self.extracted_cookies["X-dbs-session-token"]

    @cached_property
    def dbs_cust_sysgen_id(self) -> str:
        return self.extracted_cookies["X-dbs-cust-sysgen-id"]

    @property
    def common_headers(self) -> dict:
        headers = {
            "authorization": "auth",
            "authtype": "2FA",
            "channelid": "DIB",
            "clientid": "DIB",
            "user-agent": self.user_agent,
            "x-correlationid": str(uuid4()),
            "x-dbs-session-token": self.dbs_session_token,
            "x-dbs-app-code": "IWSB",
            "x-dbs-authtype": "2FA",
            "x-dbs-channel-id": "DIB",
            "x-dbs-country": "SG",
            "x-dbs-cust-sysgen-id": self.dbs_cust_sysgen_id,
            "x-dbs-locale": "en",
            "x-dbs-rqclientctry": "SG",
            "x-dbs-timestamp": self.create_utc_timestamp(),
            "x-dbs-uuid": str(uuid4()),
        }
        return headers

    # pylint: disable=too-many-arguments
    def list_statements(
        self,
        from_date: str,
        to_date: str,
        statement_type: str,
        sort_order: str,
        page_size: int,
        page_number: int,
        **_,
    ) -> list[dict]:
        """
        Returns a list of all estatement records within a given time period.
        Defaults to the last 6 months, with statements sorted in
        descending order, with 10 records per page.
        """
        params: dict[str, str | int] = {
            "statementType": statement_type,
            "from": parse(from_date).strftime("%m%Y"),
            "to": parse(to_date).strftime("%m%Y"),
            "sortOrder": sort_order,
            "pageSize": page_size,
            "pageNumber": page_number,
        }

        headers = {"actionid": "LIST", "x-version": "2.0.0", **self.common_headers}

        response = requests.get(
            self.list_endpoint, params=params, headers=headers, timeout=10
        )

        records = json.loads(response.text)

        logger.info(
            "total records: %s, types: %s",
            records["totalRecords"],
            records["estatementTypes"],
        )
        return records["estatements"]

    def download_statement(self, record: StatementRecord):
        headers = {
            "actionid": "ViewEstatement",
            "x-version": "1.0.0",
            **self.common_headers,
        }

        data = {**record.model_dump(by_alias=True)}

        logger.info(
            "Downloading estatement: %s %s",
            record.statement_date,
            record.statement_type,
        )
        response = requests.post(
            self.download_endpoint, headers=headers, json=data, timeout=10
        )

        return response.content
