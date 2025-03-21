from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_bedrock as bedrock,
    aws_lambda as lambda_,
    aws_s3 as s3,
    CfnOutput,
    Fn,
    Duration,
    CfnResource
)
from constructs import Construct

class RAGStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, s3_bucket, bedrock_role_arn, opensearch_stack=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Konfiguracja Knowledge Base
        embedding_model_id = "amazon.titan-embed-text-v1"
        embedding_model_arn = f"arn:aws:bedrock:{self.region}::foundation-model/{embedding_model_id}"

        # Konfiguracja wektorowej bazy wiedzy
        vector_kb_config = bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
            embedding_model_arn=embedding_model_arn
        )

        kb_config = bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
            type="VECTOR",
            vector_knowledge_base_configuration=vector_kb_config
        )

        # Utwórz własny zasób CFN Knowledge Base
        kb_properties = {
            "KnowledgeBaseConfiguration": {
                "Type": "VECTOR",
                "VectorKnowledgeBaseConfiguration": {
                    "EmbeddingModelArn": embedding_model_arn
                }
            },
            "Name": "iot-rag-knowledge-base",
            "RoleArn": bedrock_role_arn,
            "Description": "Knowledge Base for IoT RAG application"
        }

        # Jeśli mamy OpenSearch, dodaj konfigurację Storage
        if opensearch_stack:
            # Dla OpenSearch Serverless (jeśli używamy tej wersji)
            try:
                # Próbujemy pobrać kolekcję OpenSearch Serverless
                opensearch_collection_arn = opensearch_stack.opensearch_collection.attr_arn

                kb_properties["StorageConfiguration"] = {
                    "Type": "OPENSEARCH_SERVERLESS",
                    "OpensearchServerlessConfiguration": {
                        "CollectionArn": opensearch_collection_arn,
                        "VectorIndexName": "iot-vector-index",
                        "FieldMapping": {
                            "VectorField": "vector",
                            "TextField": "text",
                            "MetadataField": "metadata"
                        }
                    }
                }
            except AttributeError:
                # Jeśli to standardowy OpenSearch (a nie Serverless), nie używamy konfiguracji Storage
                pass

        self.knowledge_base = CfnResource(
            self, "RAGKnowledgeBase",
            type="AWS::Bedrock::KnowledgeBase",
            properties=kb_properties
        )

        # Pobierz ID knowledge base z atrybutu
        knowledge_base_id = Fn.get_att("RAGKnowledgeBase", "KnowledgeBaseId").to_string()

        # Utworzenie Data Source dla Knowledge Base
        # Konfiguracja chunkowania
        chunking_config = bedrock.CfnDataSource.ChunkingConfigurationProperty(
            chunking_strategy="FIXED_SIZE",
            fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                max_tokens=1024,
                overlap_percentage=10
            )
        )

        vector_ingestion_config = bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
            chunking_configuration=chunking_config
        )

        # Konfiguracja źródła danych S3
        s3_data_source_config = bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
            bucket_arn=s3_bucket.bucket_arn
        )

        data_source_config = bedrock.CfnDataSource.DataSourceConfigurationProperty(
            s3_configuration=s3_data_source_config,
            type="S3"
        )

        # Utworzenie Data Source
        self.data_source = bedrock.CfnDataSource(
            self, "RAGDataSource",
            data_source_configuration=data_source_config,
            knowledge_base_id=knowledge_base_id,
            name="iot-rag-data-source",
            data_deletion_policy="DELETE",
            description="Data source for IoT RAG application",
            vector_ingestion_configuration=vector_ingestion_config
        )

        # Eksport wartości do innych stacków
        CfnOutput(
            self, "KnowledgeBaseId",
            value=knowledge_base_id,
            export_name=f"{self.stack_name}:KnowledgeBaseId"
        )