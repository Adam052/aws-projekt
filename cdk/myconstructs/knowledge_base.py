from constructs import Construct
from aws_cdk import (
    aws_bedrock as bedrock,
    aws_iam as iam,
    aws_s3 as s3,
)

class KnowledgeBase(Construct):
    def __init__(self, scope: Construct, id: str, *,
                 bucket: s3.IBucket,
                 collection_arn: str,
                 account: str,
                 region: str,
                 existing_role: iam.IRole = None,
                 name: str = None,
                 description: str = None,
                 **kwargs):
        super().__init__(scope, id, **kwargs)

        self.account = account
        self.region = region
        self.knowledge_base_role = existing_role

        # Utwórz knowledge base
        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self, "Default",
            name=name,
            description=description or "Bedrock Knowledge Base for IoT data",
            role_arn=self.knowledge_base_role.role_arn,
            knowledge_base_configuration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v1"
                }
            },
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="OPENSEARCH_SERVERLESS",
                opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                    collection_arn=collection_arn,
                    field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                        metadata_field="metadata",
                        text_field="text",
                        vector_field="vector"
                    ),
                    vector_index_name="bedrock-kb-index"
                )
            )
        )

        self.knowledge_base_role.assume_role_policy.add_statements(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("bedrock.amazonaws.com")],
                actions=["sts:AssumeRole"],
                conditions={
                    "StringEquals": {
                        "aws:SourceAccount": self.account
                    },
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"
                    }
                }
            )
        )