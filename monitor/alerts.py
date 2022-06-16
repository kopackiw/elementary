import json
from exceptions.exceptions import InvalidAlertType
from utils.time import convert_utc_time_to_local_time
from datetime import datetime
from clients.slack.slack_client import SlackClient
import re


class Alert(object):
    def __init__(self, alert_id, model_unique_id, status) -> None:
        self.alert_id = alert_id
        self.model_unique_id = model_unique_id
        self.alert_status = status

    @staticmethod
    def create_alert_from_row(alert_row: dict) -> 'Alert':
        alert_type = alert_row.get('alert_type')
        if alert_type == 'dbt_test':
            return DbtTestAlert(*alert_row.values())
        else:
            return ElementaryDataAlert(*alert_row.values())
    
    @staticmethod
    def send(
        message: str = None,
        attachments: list = None,
        blocks: list = None,
        slack_token: str = None,
        channel_name: str = None,
        slack_webhook: str = None
    ) -> bool:
        slack_client = SlackClient.initial(token=slack_token, webhook=slack_webhook)
        sent_successfully = slack_client.send_message(
            channel_name=channel_name,
            message=message,
            attachments=attachments,
            blocks=blocks
        )
        return sent_successfully

    def to_slack_message(self) -> dict:
        pass

    def to_slack_workflows_message(self) -> dict:
        pass

    def to_dict(self) -> dict:
        pass

    def get_detection_time_utc(self):
        pass

    @property
    def status(self):
        return self.alert_status.lower()

    @staticmethod
    def add_fields_section_to_slack_message(slack_message: dict, section_msgs: list, divider: bool = False):
        fields = []
        for section_msg in section_msgs:
            fields.append({
                    "type": "mrkdwn",
                    "text": section_msg
            })

        block = []
        if divider:
            block.append({"type": "divider"})
        block.append({"type": "section", "fields": fields})
        slack_message['attachments'][0]['blocks'].extend(block)

    @staticmethod
    def add_text_section_to_slack_message(slack_message: dict, section_msg: str, divider: bool = False):
        block = []
        if divider:
            block.append({"type": "divider"})
        block.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": section_msg
            }
        })
        slack_message['attachments'][0]['blocks'].extend(block)

    def send_to_slack(
        self,
        slack_token: str = None,
        channel_name: str = None,
        slack_webhook: str = None,
        is_slack_workflow: bool = False
    ) -> bool:
        if is_slack_workflow:
            # Only webhooks support slack workflows
            message = json.dumps(self.to_slack_workflows_message())
            return self.send(
                slack_webhook=slack_webhook,
                message=message
            )
        else:
            attachments = self.to_slack_message()["attachments"]
            return self.send(
                slack_token=slack_token,
                channel_name=channel_name,
                slack_webhook=slack_webhook,
                attachments=attachments
            )

    @staticmethod
    def display_name(str_value):
        return ' '.join([word[0].upper() + word[1:] for word in str_value.split('_')])

    @property
    def id(self) -> str:
        return self.alert_id


class DbtTestAlert(Alert):

    def __init__(self, alert_id, model_unique_id, test_unique_id, detected_at, database_name, schema_name, table_name, column_name, alert_type, sub_type,
                 alert_description, owners, tags, alert_results_query, alert_results, other, test_name, test_params,
                 severity, status) -> None:
        super().__init__(alert_id, model_unique_id, status)
        self.test_unique_id = test_unique_id
        self.alert_type = alert_type
        self.alert_title = "dbt test alert"
        self.database_name = database_name
        self.schema_name = schema_name
        self.table_name = table_name
        self.table_unique_id = '.'.join([database_name, schema_name, table_name]).lower()
        self.detected_at = None
        if detected_at:
            self.detected_at_utc = datetime.fromisoformat(detected_at)
            self.detected_at = convert_utc_time_to_local_time(self.detected_at_utc).strftime('%Y-%m-%d %H:%M:%S')
        self.owners = json.loads(owners) if owners else ''
        if isinstance(self.owners, list):
            self.owners = ', '.join(self.owners)
        self.tags = json.loads(tags) if tags else ''
        if isinstance(self.tags, list):
            self.tags = [f'#{tag}' for tag in self.tags]
            self.tags = ', '.join(self.tags)
        self.test_name = test_name
        self.test_display_name = self.display_name(test_name)
        self.other = other
        self.sub_type = sub_type
        self.sub_type_value = self.display_name(self.sub_type)
        self.alert_results_query = alert_results_query.strip() if alert_results_query else ''
        self.alert_results = alert_results if alert_results else ''
        self.test_params = test_params
        self.error_message = alert_description if alert_description else 'No error message'
        self.column_name = column_name if column_name else ''
        self.icon = ':small_red_triangle:'
        #TODO: change this to be based on status
        if severity and severity.lower() == 'warn':
            self.icon = ':warning:'
        self.test_results = None
        if status != 'pass':
            found_rows_number = re.search(r'\d+', self.error_message)
            self.failed_rows_count = -1
            if found_rows_number:
                found_rows_number = found_rows_number.group()
                self.failed_rows_count = int(found_rows_number)
            self.test_results = {'display_name': self.test_display_name + ' - failed results sample',
                                 'results_sample': self.alert_results,
                                 'error_message': self.error_message,
                                 'failed_rows_count': self.failed_rows_count}

    def get_detection_time_utc(self):
        return self.detected_at_utc

    def to_slack_message(self) -> dict:
        slack_message = {
            "attachments": [
                {
                    "blocks": [
                    ]
                }
            ]
        }

        self.add_text_section_to_slack_message(slack_message, f"{self.icon} *{self.alert_title}*")

        self.add_fields_section_to_slack_message(slack_message,
                                                 [f"*Table:*\n{self.table_unique_id}", f"*When:*\n{self.detected_at}"],
                                                 divider=True)

        self.add_fields_section_to_slack_message(slack_message,
                                                 [f"*Status:*\n{self.alert_status}", f"*Test name:*\n{self.test_name}"])

        self.add_fields_section_to_slack_message(slack_message, [f"*Owners:*\n{self.owners}", f"*Tags:*\n{self.tags}"])

        if self.error_message:
            self.add_text_section_to_slack_message(slack_message,
                                                   f"*Error message:*\n{self.error_message}",
                                                   divider=True)

        if self.column_name:
            self.add_text_section_to_slack_message(slack_message, f"*Column:*\n{self.column_name}", divider=True)

        if self.test_params:
            self.add_text_section_to_slack_message(slack_message,
                                                   f"*Test Parameters:*\n`{self.test_params}`",
                                                   divider=True)

        if self.alert_results_query:
            self.add_text_section_to_slack_message(slack_message,
                                                   f"*Test Query:*\n```{self.alert_results_query}```",
                                                   divider=True)

        if self.alert_results:
            self.add_text_section_to_slack_message(slack_message,
                                                   f"*Test Results Sample:*\n`{self.alert_results}`",
                                                   divider=True)

        return slack_message

    def to_slack_workflows_message(self) -> dict:
        return {
            'alert_title': self.alert_title,
            'alert_type': self.alert_type,
            'table_name': self.table_unique_id,
            'detected_at': self.detected_at,
            'owners': self.owners,
            'tags': self.tags,
            'test_name': self.test_name,
            'status': self.alert_status,
            'alert_results_query': self.alert_results_query,
            'alert_results': self.alert_results,
            'test_params': self.test_params,
            'error_message': self.error_message,
            'column_name': self.column_name
        }

    def to_dict(self):
        #TODO: maybe redundant with slack workflows
        return {'test_unique_id': self.test_unique_id,
                'database_name': self.database_name,
                'schema_name': self.schema_name,
                'table_name': self.table_name,
                'column_name': self.column_name,
                'test_name': self.test_name,
                'test_display_name': self.test_display_name,
                'latest_run_time': self.detected_at,
                'latest_run_time_utc': self.detected_at_utc.strftime('%Y-%m-%d %H:%M:%S'),
                'latest_run_status': self.alert_status,
                'model_unique_id': self.model_unique_id,
                'table_unique_id': self.table_unique_id,
                'test_type': self.alert_type,
                'test_sub_type': self.sub_type,
                'test_query': self.alert_results_query,
                'test_params': self.test_params,
                'test_results': self.test_results}


class ElementaryDataAlert(DbtTestAlert):
    def __init__(self, alert_id, model_unique_id, test_unique_id, detected_at, database_name, schema_name, table_name, column_name,
                 alert_type, sub_type, alert_description, owners, tags, alert_results_query, alert_results, other,
                 test_name, test_params, severity, status) -> None:
        super().__init__(alert_id, model_unique_id, test_unique_id, detected_at, database_name, schema_name, table_name, column_name,
                         alert_type, sub_type, alert_description, owners, tags, alert_results_query, alert_results,
                         other, test_name, test_params, severity, status)

        self.anomalous_value = None
        if self.alert_type == 'schema_change':
            self.alert_title = 'Schema change detected'
            self.sub_type_title = 'Change Type'
        elif self.alert_type == 'anomaly_detection':
            self.alert_title = 'Data anomaly detected'
            self.sub_type_title = 'Anomaly Type'
            self.anomalous_value = self.other if self.other else None
        else:
            raise InvalidAlertType(f'Got invalid alert type - {self.alert_type}')

        self.description = alert_description[0].upper() + alert_description[1:].lower() if alert_description else ''
        test_params = json.loads(test_params) if test_params else {}
        self.test_params = {'timestamp_column': test_params.get('timestamp_column')}
        self.metrics_unit = self.get_metrics_unit(self.sub_type)
        self.test_results = None
        if self.alert_type == 'anomaly_detection':
            self.test_params['anomaly_threshold'] = test_params.get('anomaly_score_threshold')
            self.test_results = {'display_name': self.sub_type_value,
                                 'metrics': self.alert_results,
                                 'metrics_unit': self.metrics_unit,
                                 'result_description': self.description}
        elif self.alert_type == 'schema_change':
            self.test_results = {'display_name': self.sub_type_value.lower(),
                                 'result_description': self.description}


    @staticmethod
    def get_metrics_unit(metric_name):
        lower_metric_name = metric_name.lower()
        if 'count' in lower_metric_name:
            return 'Count'
        elif 'percent' in lower_metric_name:
            return 'Percentage'
        elif 'freshness' in lower_metric_name:
            return 'Hours'
        else:
            metrics_unit = metric_name.split('_')[0]
            return metrics_unit[0].upper() + metrics_unit[1].lower()

    def to_slack_message(self) -> dict:
        slack_message = {
            "attachments": [
                {
                    "blocks": [
                    ]
                }
            ]
        }

        self.add_text_section_to_slack_message(slack_message, f"{self.icon} *{self.alert_title}*")

        self.add_fields_section_to_slack_message(slack_message,
                                                 [f"*Table:*\n{self.table_unique_id}", f"*When:*\n{self.detected_at}"],
                                                 divider=True)

        self.add_fields_section_to_slack_message(slack_message,
                                                 [f"*Test name:*\n{self.test_name}",
                                                  f"*{self.sub_type_title}:*\n{self.sub_type_value}"])

        self.add_fields_section_to_slack_message(slack_message, [f"*Owners:*\n{self.owners}", f"*Tags:*\n{self.tags}"])

        if self.description:
            self.add_text_section_to_slack_message(slack_message, f"*Description:*\n{self.description}", divider=True)

        column_msgs = []
        if self.column_name:
            column_msgs.append(f"*Column:*\n{self.column_name}")
        if self.anomalous_value:
            column_msgs.append(f"*Anomalous Value:*\n{self.anomalous_value}")

        if column_msgs:
            self.add_fields_section_to_slack_message(slack_message, column_msgs, divider=True)

        if self.test_params:
            self.add_text_section_to_slack_message(slack_message,
                                                   f"*Test Parameters:*\n{self.test_params}",
                                                   divider=True)

        return slack_message

    def to_slack_workflows_message(self) -> dict:
        return {
            'alert_description': self.alert_title,  # backwards
            'alert_title': self.alert_title,
            'alert_type': self.alert_type,
            'table_name': self.table_unique_id,
            'detected_at': self.detected_at,
            'owners': self.owners,
            'tags': self.tags,
            'test_name': self.test_name,
            'status': self.alert_status,
            'alert_results_query': self.alert_results_query,
            'alert_results': self.alert_results,
            'test_params': self.test_params,
            'description': self.description,  # backwards
            'sub_type': self.sub_type_value,
            'type': self.sub_type_value,   # backwards
            'column_name': self.column_name
        }

    def to_dict(self):
        #TODO: maybe redundant with slack workflows
        return {'test_unique_id': self.test_unique_id,
                'database_name': self.database_name,
                'schema_name': self.schema_name,
                'table_name': self.table_name,
                'column_name': self.column_name,
                'test_name': self.test_name,
                'test_display_name': self.test_display_name,
                'latest_run_time': self.detected_at,
                'latest_run_time_utc': self.detected_at_utc.strftime('%Y-%m-%d %H:%M:%S'),
                'latest_run_status': self.alert_status,
                'model_unique_id': self.model_unique_id,
                'table_unique_id': self.table_unique_id,
                'test_type': self.alert_type,
                'test_sub_type': self.sub_type_value,
                'test_query': self.alert_results_query,
                'test_params': self.test_params,
                'test_results': self.test_results}