from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_bedrock as bedrock,
    CfnOutput,
    Fn
)
from constructs import Construct

class BedrockStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Utworzenie roli dla Bedrock
        self.bedrock_role = iam.Role(
            self, "BedrockServiceRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Role for Amazon Bedrock service"
        )

        # Dodanie polityk dostępu
        self.bedrock_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["*"],
                actions=[
                    "bedrock:ListFoundationModels",
                    "bedrock:ListCustomModels",
                    "bedrock:InvokeModel"
                ]
            )
        )

        # Dodanie polityki dostępu do S3
        self.bedrock_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["arn:aws:s3:::*", "arn:aws:s3:::*/*"],
                actions=["s3:GetObject", "s3:ListBucket"]
            )
        )

        # Eksport wartości do innych stacków
        CfnOutput(
            self, "BedrockRoleArn",
            value=self.bedrock_role.role_arn,
            export_name=f"{self.stack_name}:BedrockRoleArn"
        )