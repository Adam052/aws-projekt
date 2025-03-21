from aws_cdk import (
    Stack,
    aws_opensearchservice as opensearch,
    aws_ec2 as ec2,
    aws_iam as iam,
    RemovalPolicy,
    CfnOutput,
    CustomResource,
    aws_lambda as lambda_,
    custom_resources as cr
)
from constructs import Construct

class OpenSearchStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, vpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a service-linked role for OpenSearch Service first
        slr_provider = cr.Provider(
            self, "ServiceLinkedRoleProvider",
            on_event_handler=lambda_.Function(
                self, "CreateServiceLinkedRoleFunction",
                runtime=lambda_.Runtime.PYTHON_3_9,
                handler="index.handler",
                code=lambda_.Code.from_inline("""
import boto3
import cfnresponse
import time

def handler(event, context):
    response_data = {}

    if event['RequestType'] == 'Create':
        try:
            # Create the service-linked role for OpenSearch
            iam_client = boto3.client('iam')
            iam_client.create_service_linked_role(
                AWSServiceName='opensearchservice.amazonaws.com',
                Description='Service-linked role for OpenSearch Service'
            )
            # Wait a bit for the role to be fully created
            time.sleep(10)
            response_data['Message'] = 'Service-linked role created'
        except Exception as e:
            # If the role already exists, this is fine
            if 'Role already exists' in str(e):
                response_data['Message'] = 'Service-linked role already exists'
            else:
                print(f"Error creating service-linked role: {str(e)}")
                cfnresponse.send(event, context, cfnresponse.FAILED, {'Error': str(e)})
                return

    cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
""")
            )
        )

        # Create the custom resource that will create the service-linked role
        slr_custom_resource = CustomResource(
            self, "ServiceLinkedRoleCustomResource",
            service_token=slr_provider.service_token
        )

        # Utworzenie security group dla OpenSearch
        self.security_group = ec2.SecurityGroup(
            self, "OpenSearchSecurityGroup",
            vpc=vpc,
            description="Security group for OpenSearch domain",
            allow_all_outbound=True
        )

        # Dodanie reguły wejściowej dla ruchu HTTPS
        self.security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            "Allow HTTPS traffic"
        )

        # Utworzenie roli dostępu dla OpenSearch
        self.opensearch_role = iam.Role(
            self, "OpenSearchRole",
            assumed_by=iam.ServicePrincipal("opensearchservice.amazonaws.com")
        )

        # Dodanie polityki dostępu do OpenSearch
        self.opensearch_role.add_to_policy(
            iam.PolicyStatement(
                actions=["es:*"],
                resources=["*"]
            )
        )

        # Wybierz dokładnie jedną podsieć (pierwszą z prywatnych)
        private_subnets = vpc.private_subnets
        if not private_subnets:
            raise ValueError("VPC musi mieć co najmniej jedną prywatną podsieć")

        selected_subnet = private_subnets[0]

        # Utworzenie domeny OpenSearch
        self.opensearch_domain = opensearch.Domain(
            self, "OpenSearchDomain",
            version=opensearch.EngineVersion.OPENSEARCH_2_5,
            vpc=vpc,
            vpc_subnets=[ec2.SubnetSelection(subnets=[selected_subnet])],  # Wybierz dokładnie jedną podsieć
            security_groups=[self.security_group],
            capacity=opensearch.CapacityConfig(
                data_node_instance_type="t3.small.search",
                data_nodes=1
            ),
            ebs=opensearch.EbsOptions(
                enabled=True,
                volume_size=10,
                volume_type=ec2.EbsDeviceVolumeType.GP2
            ),
            node_to_node_encryption=True,
            encryption_at_rest=opensearch.EncryptionAtRestOptions(
                enabled=True
            ),
            enforce_https=True,
            removal_policy=RemovalPolicy.DESTROY,
            access_policies=[
                iam.PolicyStatement(
                    actions=["es:*"],
                    resources=["*"],
                    principals=[iam.AnyPrincipal()]
                )
            ]
        )

        # Make sure the domain depends on the service-linked role creation
        self.opensearch_domain.node.add_dependency(slr_custom_resource)

        # Dodanie polityki dostępu dla Bedrock
        self.bedrock_access_policy = iam.PolicyStatement(
            actions=["es:ESHttpGet", "es:ESHttpPut", "es:ESHttpPost", "es:ESHttpDelete"],
            resources=[f"{self.opensearch_domain.domain_arn}/*"],
            principals=[iam.ServicePrincipal("bedrock.amazonaws.com")]
        )

        # Eksport wartości do innych stacków
        CfnOutput(
            self, "OpenSearchDomainEndpoint",
            value=self.opensearch_domain.domain_endpoint,
            export_name=f"{self.stack_name}:OpenSearchDomainEndpoint"
        )

        CfnOutput(
            self, "OpenSearchDomainArn",
            value=self.opensearch_domain.domain_arn,
            export_name=f"{self.stack_name}:OpenSearchDomainArn"
        )