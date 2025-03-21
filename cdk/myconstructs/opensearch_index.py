from aws_cdk import (
    CustomResource,
    Duration,
    aws_lambda,
    aws_iam as iam,
    aws_logs as logs,
    custom_resources,
    aws_opensearchserverless as aoss,
    RemovalPolicy,
)
from constructs import Construct
import datetime
import os
import tempfile
import json
import pathlib
import boto3
import time

class OpenSearchIndex(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str, *,
        collection_id: str,
        index_name: str = "bedrock-kb-index",
        vector_field: str = "vector",
        text_field: str = "text",
        metadata_field: str = "metadata",
        **kwargs
    ):
        super().__init__(scope, id, **kwargs)

        # Utwórz rolę dla lambdy
        lambda_role = iam.Role(
            self, "IndexCreatorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSLambda_ReadOnlyAccess"),
            ]
        )

        # Dodaj uprawnienia do roli Lambda
        lambda_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["aoss:*"],
            resources=["*"]
        ))

        # Usuń poprzednie polityki i zastąp je jedną polityką z prawidłowymi uprawnieniami
        access_policy = aoss.CfnAccessPolicy(
            self, "AccessPolicy",
            name=f"acs-{collection_id}",
            type="data",
            policy=json.dumps([{
                "Description": "Access policy for OpenSearch",
                "Rules": [
                    {
                        "ResourceType": "index",
                        "Resource": [f"index/{collection_id}/*"],
                        "Permission": [
                            "aoss:ReadDocument",
                            "aoss:WriteDocument",
                            "aoss:CreateIndex",
                            "aoss:DeleteIndex",
                            "aoss:UpdateIndex",
                            "aoss:DescribeIndex",
                            "aoss:*"
                        ]
                    }
                ],
                "Principal": [lambda_role.role_arn]
            }])
        )

        # Dodaj zależność
        access_policy.node.add_dependency(lambda_role)

        # Przygotuj kod Lambda
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Utwórz plik index.py
            with open(os.path.join(tmp_dir, "index.py"), "w") as f:
                f.write("""
import json
import os
import boto3
import time
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

def handler(event, context):
    print(f"Event: {json.dumps(event)}")

    # Pobierz właściwości z eventu
    props = event.get('ResourceProperties', {})
    endpoint_id = props.get('OPENSEARCH_ENDPOINT_ID')
    index_name = props.get('INDEX_NAME')
    vector_field = props.get('VECTOR_FIELD_NAME')
    text_field = props.get('TEXT_FIELD_NAME')
    metadata_field = props.get('METADATA_NAME')

    print(f"Configuration: endpoint_id={endpoint_id}, index_name={index_name}")

    # Konfiguracja klienta OpenSearch
    region = os.environ.get('AWS_REGION', 'eu-central-1')
    service = 'aoss'

    print("Waiting for permissions to propagate...")
    time.sleep(30)

    try:
        # Sprawdź status kolekcji
        aoss_client = boto3.client('opensearchserverless')
        print(f"Checking collection status for {endpoint_id}...")

        # Dodaj listowanie wszystkich kolekcji dla debugowania
        all_collections = aoss_client.list_collections()
        print(f"All collections: {json.dumps(all_collections)}")

        # Sprawdź polityki dostępu
        access_policies = aoss_client.list_access_policies()
        print(f"Access policies: {json.dumps(access_policies)}")

        response = aoss_client.batch_get_collection(ids=[endpoint_id])
        print(f"Collection details: {json.dumps(response)}")

        if not response['collectionDetails']:
            raise Exception(f"Collection {endpoint_id} not found")

        collection_status = response['collectionDetails'][0]['status']
        print(f"Collection status: {collection_status}")

        if collection_status != 'ACTIVE':
            raise Exception(f"Collection {endpoint_id} is not active yet. Status: {collection_status}")

        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, region, service)

        host = f"{endpoint_id}.{region}.aoss.amazonaws.com"
        client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20
        )

        if event['RequestType'] == 'Create':
            index_body = {
                "settings": {
                    "index": {
                        "knn": True,
                        "knn.algo_param.ef_search": 512
                    }
                },
                "mappings": {
                    "properties": {
                        vector_field: {
                            "type": "knn_vector",
                            "dimension": 1536,
                            "method": {
                                "name": "hnsw",
                                "engine": "faiss",
                                "space_type": "l2"
                            }
                        },
                        text_field: {
                            "type": "text"
                        },
                        metadata_field: {
                            "type": "text"
                        }
                    }
                }
            }

            try:
                # Sprawdź czy indeks już istnieje
                if not client.indices.exists(index=index_name):
                    response = client.indices.create(
                        index=index_name,
                        body=index_body
                    )
                    print(f"Index created successfully: {json.dumps(response)}")
                else:
                    print(f"Index {index_name} already exists")

                return {
                    'PhysicalResourceId': f"index-{index_name}",
                    'Data': {
                        'IndexName': index_name
                    }
                }
            except Exception as e:
                print(f"Error: {str(e)}")
                raise e

        elif event['RequestType'] == 'Delete':
            try:
                response = client.indices.delete(index=index_name)
                print(f"Index deleted successfully: {json.dumps(response)}")
                return {
                    'PhysicalResourceId': event['PhysicalResourceId']
                }
            except Exception as e:
                print(f"Error deleting index: {str(e)}")
                raise e
    except Exception as e:
        print(f"Error checking collection status: {str(e)}")
        raise e
""")

            # Utwórz requirements.txt
            with open(os.path.join(tmp_dir, "requirements.txt"), "w") as f:
                f.write("""
opensearch-py>=2.0.0
requests-aws4auth>=1.0.0
boto3>=1.26.0
""")

            # Lambda do utworzenia indeksu
            index_creator = aws_lambda.Function(
                self, "IndexCreator",
                runtime=aws_lambda.Runtime.PYTHON_3_9,
                handler="index.handler",
                code=aws_lambda.Code.from_asset(
                    path=tmp_dir,
                    bundling={
                        "image": aws_lambda.Runtime.PYTHON_3_9.bundling_image,
                        "command": [
                            "bash", "-c",
                            "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output"
                        ]
                    }
                ),
                timeout=Duration.minutes(2),
                role=lambda_role,
                memory_size=3008
            )

            index_creator.apply_removal_policy(RemovalPolicy.DESTROY)

        # Utwórz provider
        provider = custom_resources.Provider(
            self, "IndexProvider",
            on_event_handler=index_creator
        )

        # Utwórz custom resource
        self.custom_resource = CustomResource(
            self, "Index",
            service_token=provider.service_token,
            properties={
                "OPENSEARCH_ENDPOINT_ID": collection_id,
                "INDEX_NAME": index_name,
                "VECTOR_FIELD_NAME": vector_field,
                "TEXT_FIELD_NAME": text_field,
                "METADATA_NAME": metadata_field,
                "TIMESTAMP": datetime.datetime.now().isoformat()
            }
        )