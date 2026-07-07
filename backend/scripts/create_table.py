"""Create the table on DynamoDB Local for development.

    docker run -p 8000:8000 amazon/dynamodb-local
    DYNAMO_ENDPOINT_URL=http://localhost:8000 python scripts/create_table.py
"""

import boto3

from app.config import settings
from app.repo.schema import create_table

endpoint = settings.dynamo_endpoint_url or "http://localhost:8000"
client = boto3.client("dynamodb", endpoint_url=endpoint, region_name="us-east-1")
create_table(client, settings.table_name)
print(f"Created table {settings.table_name} at {endpoint}")
