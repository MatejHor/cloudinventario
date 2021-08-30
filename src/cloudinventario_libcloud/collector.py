import logging
from pprint import pprint

from libcloud.compute.providers import get_driver

from cloudinventario.helpers import CloudCollector, CloudInvetarioResourceManager

# TEST MODE
TEST = 0


def setup(name, config, defaults, options):
    return CloudCollectorLibcloud(name, config, defaults, options)


class CloudCollectorLibcloud(CloudCollector):
    def __init__(self, name, config, defaults, options):
        super().__init__(name, config, defaults, options)

    def _config_keys():
        return {
            zone: 'Zone of project',
            region: 'Region of project',
            project: 'Project name, only for GCP',

            driver: 'Driver type for gcp (gce), aws (ec2), Required',
            first_param: 'First parameters (client_email, access_key), Required',
            second_param: 'Second parameters (private_key, secret_key), Required',
        }

    def _get_dependencies(self):
        return []

    def _is_not_primitive(self, obj):
        return hasattr(obj, '__dict__')

    def _login(self):
        # Get zone or region for cluster field
        self.zone = self.config['additional_params']['zone'] if 'zone' in self.config['additional_params'] else self.config[
            'additional_params']['region'] if 'region' in self.config['additional_params'] else None
        self.project_name = self.config['additional_params'].get('project')
        # Load driver to get provider
        ComputeEngine = get_driver(self.config['driver'])

        self.driver = ComputeEngine(
            self.config['first_param'],
            self.config['second_param'],
            # Pass every additional attribute as dict into computeEngine
            **self.config['additional_params']
        )

        logging.info("logging config for {} driver type".format(self.config['driver']))
        return self.driver

    def _fetch(self, collect):
        data = []
        instances = self.driver.list_nodes()

        for instance in instances:
            # Process instance
            data.append(self._process_vm(instance))
        # [self._process_vm(instance) for instance in instances]

        logging.info("Collected {} vm".format(len(data)))
        return data

    def _process_vm(self, rec):
        # Attribute to remove from instance
        to_remove = dict()

        # To check if some attribute is object (or array of object) to give every information
        for key in rec.extra:
            item = rec.extra[key]
            # If field is object
            if self._is_not_primitive(item):
                attributes = dict()
                for attribute in item.__dict__.items():
                    attributes[attribute[0]] = attribute[1]
                to_remove[key] = str(attributes)
            # If field is array of object (need to check first item other will be the same type as first one)
            elif isinstance(item, list) and len(item) > 0 and self._is_not_primitive(item[0]):
                for object in item:
                    attributes = dict()
                    for attribute in object.__dict__.items():
                        attributes[attribute[0]] = attribute[1]
                    to_remove[key] = str(attributes)

        # Remove key from instance and add object data
        for key in to_remove:
            del rec.extra[key]
            rec.extra[key] = to_remove[key]

        logging.info("new VM name={}".format(rec.name))
        vm_data = {
            "id": rec.id,
            "created": rec.created_at,
            "name": rec.name,
            "size": rec.size,
            "image": rec.image,
            "cluster": self.zone,
            "project": self.project_name,
            "primary_ip": rec.public_ips[0] if len(rec.public_ips) > 0 else None,
            "public_ip": rec.public_ips,
            "status": rec.state,
            "is_on": rec.state.lower() == 'running',
            "tags": rec.extra['labels'] if 'labels' in rec.extra else rec.extra.get('tags'),
            "extra": rec.extra,
        }
        return self.new_record('vm', vm_data, vm_data)

    def _logout(self):
        self.driver = None
