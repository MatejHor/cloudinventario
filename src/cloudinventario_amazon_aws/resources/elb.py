import boto3, json
from pprint import pprint

from cloudinventario.helpers import CloudInvetarioResource

def setup(resource, collector):
  return CloudInventarioElb(resource, collector)

class CloudInventarioElb(CloudInvetarioResource):

  def __init__(self, resource, collector):
    super().__init__(resource, collector)

  def _login(self, session):
    self.session = session
    self.client = self.get_client()

  def _get_client(self):
    client = self.session.client('elb')
    return client

  def _fetch(self):
    data = []
    paginator = self.client.get_paginator('describe_load_balancers')
    response_iterator = paginator.paginate()

    marker = None
    while True:
      if marker:
        response_iterator = self.client.describe_load_balancers(Marker=marker)
      else:
        response_iterator = self.client.describe_load_balancers()

      for lb in response_iterator['LoadBalancerDescriptions']:
        data.append(self.process_resource(lb))

      try:
        marker = response_iterator['Marker']
      except Exception:
        break

    return data

  def _process_resource(self, balancer):
    health_info = self.client.describe_instance_health(LoadBalancerName=balancer['LoadBalancerName'])
    health_states = {}
    status = "unknown"

    for instance in health_info['InstanceStates']:
      state = instance['State']
      if state == "InService": # if any in service, service is on
        status = "on"
      elif status == "unknown" and state == "OutOfService":
        status = "off"
      elif status == "unknown" and state == "Unknown":
        status = "unknown"

      health_states[instance['InstanceId']] = {
        "state": instance['State']
      }

    data = {
      "created": balancer['CreatedTime'],
      "name": balancer['LoadBalancerName'],
      "cluster": balancer['AvailabilityZones'],
      "id": balancer['CanonicalHostedZoneNameID'],
      "instances": health_states,
      "public_fqdn": balancer['CanonicalHostedZoneName'],
      "owner": self.collector.account_id,
      "status": health_states,
      "is_on": True if status == "on" else False,
      "scheme": balancer['Scheme'],
      "subnets": balancer['Subnets']
    }

    return self.new_record(self.res_type, data, balancer)
