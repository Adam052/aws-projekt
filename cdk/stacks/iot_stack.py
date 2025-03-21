from aws_cdk import (
    Stack,
    aws_iot as iot,
    aws_iam as iam,
    CfnOutput,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct
from aws_cdk.aws_iot import CfnTopicRule

class IoTStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, msk_stack=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        if msk_stack:
            self.add_dependency(msk_stack)

        # Dodaj endpoint jako atrybut klasy
        self.iot_endpoint = f"{self.account}.iot.{self.region}.amazonaws.com"

        # Tworzenie IoT Policy
        iot_policy = iot.CfnPolicy(
            self, "CorePolicy",
            policy_name="iot-device-policy",
            policy_document={
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "iot:Connect",
                        "iot:Publish",
                        "iot:Subscribe",
                        "iot:Receive"
                    ],
                    "Resource": ["*"]
                }]
            }
        )

        # Tworzenie roli dla IoT
        iot_role = iam.Role(
            self, "IoTRole",
            assumed_by=iam.ServicePrincipal("iot.amazonaws.com")
        )
        iot_role.node.add_metadata("DeletionPolicy", "Delete")

        # Sekrety dla połączenia SSL
        keystore_secret = secretsmanager.Secret(
            self, "KeystoreSecret",
            secret_name="iot/keystore",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                generate_string_key="keystore",
                secret_string_template='{"keystore":"dummy"}'
            )
        )

        keystore_password_secret = secretsmanager.Secret(
            self, "KeystorePasswordSecret",
            secret_name="iot/keystore_password",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                generate_string_key="password",
                secret_string_template='{"password":"dummy"}'
            )
        )

        # Uprawnienia do MSK
        if msk_stack:
            # Upewnij się, że ARN klastra jest poprawny
            msk_cluster_arn = f"arn:aws:kafka:{self.region}:{self.account}:cluster/{msk_stack.cluster.cluster_name}/{msk_stack.cluster.cluster_arn.split('/')[-1]}"

            iot_role.add_to_policy(iam.PolicyStatement(
                actions=["kafka-cluster:Connect", "kafka-cluster:WriteData"],
                resources=[msk_cluster_arn]
            ))

            # Tworzenie reguły IoT
            iot_rule = CfnTopicRule(
                self, "IoTtoMSKRule",
                topic_rule_payload=CfnTopicRule.TopicRulePayloadProperty(
                    sql="SELECT * FROM 'iot/data'",
                    actions=[CfnTopicRule.ActionProperty(
                        kafka=CfnTopicRule.KafkaActionProperty(
                            destination_arn=msk_stack.cluster.cluster_arn,
                            topic="iot-data",
                            client_properties={
                                "bootstrap.servers": msk_stack.bootstrap_brokers_tls,
                                "security.protocol": "SSL",
                                "ssl.truststore": "ZHVtbXk=",
                                "ssl.keystore": keystore_secret.secret_value_from_json("keystore").to_string(),
                                "ssl.keystore.password": keystore_password_secret.secret_value_from_json("password").to_string()
                            }
                        )
                    )]
                )
            )
            iot_rule.node.add_metadata("DeletionPolicy", "Delete")

        # Output endpointu IoT
        CfnOutput(self, "IoTEndpoint",
            value=self.iot_endpoint
        )