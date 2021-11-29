import logging, re
from pprint import pprint
from datetime import datetime, timedelta
from sqlalchemy.pool import NullPool
import json

import sqlalchemy as sa

TABLE_PREFIX = "ci_"

STATUS_OK = "OK"
STATUS_FAIL = "FAIL"
STATUS_ERROR = "ERROR"

class InventoryStorage:

   def __init__(self, config):
     self.config = config
     self.dsn = config["dsn"]
     self.engine = self.__create()
     self.conn = None
     self.version = 0

   def __del__(self):
     if self.conn:
       self.disconnect()
     self.engine.dispose()

   def __create(self):
     return sa.create_engine(self.dsn, echo=False, poolclass=NullPool)

   def connect(self):
     self.conn = self.engine.connect()
     #self.conn.execution_options(autocommit=True)
     if not self.__check_schema():
       self.__create_schema()
     self.__prepare();
     return True

   def __check_schema(self):
     return False

   def __create_schema(self):
     meta = sa.MetaData()
     self.source_table = sa.Table(TABLE_PREFIX + 'source', meta,
       sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
       sa.Column('ts', sa.String, default=sa.func.now()),
       sa.Column('source', sa.String),
       sa.Column('version', sa.Integer, default=1),
       sa.Column('runtime', sa.Integer),
       sa.Column('entries', sa.Integer),
       sa.Column('status', sa.String),
       sa.Column('error', sa.Text),

       sa.UniqueConstraint('source', 'version')
     )

     self.inventory_table = sa.Table(TABLE_PREFIX + 'inventory', meta,
       sa.Column('inventory_id', sa.Integer, primary_key=True, autoincrement=True),
       sa.Column('version', sa.Integer),

       sa.Column('source', sa.String),
       sa.Column('type', sa.String),
       sa.Column('name', sa.String),
       sa.Column('cluster', sa.String),
       sa.Column('project', sa.String),
       sa.Column('location', sa.String),
       sa.Column('id', sa.String),
       sa.Column('created', sa.String),

       sa.Column('cpus', sa.Integer),
       sa.Column('memory', sa.Integer),
       sa.Column('disks', sa.Integer),
       sa.Column('storage', sa.Integer),

       sa.Column('primary_ip', sa.String),

       sa.Column('os', sa.String),
       sa.Column('os_family', sa.String),

       sa.Column('status', sa.String),
       sa.Column('is_on', sa.Integer),

       sa.Column('owner', sa.String),
       sa.Column('tags', sa.Text),

       sa.Column('networks', sa.String),
       sa.Column('storages', sa.String),

       sa.Column('description', sa.String),
       sa.Column('attributes', sa.Text),
       sa.Column('details', sa.Text),

       sa.UniqueConstraint('version', 'source', 'type', 'name', "cluster", 'project', 'id')
     )

     self.dns_record = sa.Table(TABLE_PREFIX + 'dns_record', meta,
       sa.Column('id', sa.String),
       sa.Column('name', sa.String),
       sa.Column('record_type', sa.String),
       sa.Column('domain', sa.String),
       sa.Column('ttl', sa.String),

       sa.Column('type', sa.String),
       sa.Column('source', sa.String),
       sa.Column('version', sa.Integer),

       sa.Column('data', sa.Text),

       sa.Column('attributes', sa.Text),
       sa.Column('details', sa.Text),
     )

     self.dns_domain = sa.Table(TABLE_PREFIX + 'dns_domain', meta,
       sa.Column('id', sa.String),
       sa.Column('domain', sa.String ),
       sa.Column('domain_type', sa.String),
       sa.Column('ttl', sa.String),

       sa.Column('type', sa.String),
       sa.Column('source', sa.String),
       sa.Column('version', sa.Integer),

       sa.Column('attributes', sa.Text),
       sa.Column('details', sa.Text),
     )

     meta.create_all(self.engine, checkfirst = True)
     return True

   def __prepare(self):
     pass

   def __get_sources_version_max(self):
     # get active version
     res = self.conn.execute(sa.select([
                   self.source_table.c.source,
                   sa.func.max(self.source_table.c.version).label("version")])
     	              .group_by(self.source_table.c.source))
     res = res.fetchall()
     if res and res[0]["version"]:
       sources = [dict(row) for row in res]
     else:
       sources = []
     return sources

   def __get_source_version_max(self, name):
     sources = self.__get_sources_version_max()
     for source in sources:
       if name == source["source"]:
         return source["version"]
     return 0

   def log_status(self, source, status, runtime = None, error = None):
     version = self.__get_source_version_max(source)

     data = {
       "source": source,
       "version": version + 1,
       "status": status,
       "runtime": runtime,
       "error": error
     }

     with self.engine.begin() as conn:
       conn.execute(self.source_table.insert(), data)
     return True

   def save(self, data, runtime = None):
     if data is None:
       return False

     sources = self.__get_sources_version_max()

     # increment versions
     versions = {}
     for source in sources:
       source["version"] += 1
       versions[source["source"]] = source["version"]

     # collect data sources versions
     entries = {}
     for rec in data:
       if rec["source"] not in versions.keys():
         versions[rec["source"]] = 1
         sources.append({ "source": rec["source"],
                          "version": versions[rec["source"]] })
       rec["version"] = versions.get(rec["source"], 1)
       entries.setdefault(rec["source"], 0)
       entries[rec["source"]] += 1

     # save entry counts
     sources_save = []
     for source in sources:
       if not source["source"] in entries:
         continue
       source["entries"] = entries[source["source"]]
       source["status"] = STATUS_OK
       source["runtime"] = runtime
       sources_save.append(source)
     
     # Uses dict to sorting data by their type, now only dns_record, dns_domain
     data_to_insert = dict()
     # to work normaly with every type of data (vm, storage...) remove *this
     data_to_insert['inventory_table'] = []
     for item in data:
       # * from 
       if item['type'] != 'dns_domain' and item['type'] != 'dns_record':
         data_to_insert['inventory_table'].append(item)
       else:
       # * to 
        if item['type'] not in data_to_insert:
          data_to_insert[item['type']] = []
        data_to_insert[item['type']].append(dict(item, **json.loads(item['attributes'])))

     if len(sources) == 0:
       return False

     # store data
     with self.engine.begin() as conn:
       conn.execute(self.source_table.insert(), sources_save)
       conn.execute(self.dns_record.insert(), data_to_insert['dns_record']) if 'dns_record' in data_to_insert else None
       conn.execute(self.dns_domain.insert(), data_to_insert['dns_domain']) if 'dns_domain' in data_to_insert else None
       conn.execute(self.inventory_table.insert(), data_to_insert['inventory_table'])
     return True

   def cleanup(self, days):
     res = self.conn.execute(sa.select([
                   self.source_table.c.source,
                   self.source_table.c.version])
		.where(self.source_table.c.ts <= datetime.today() - timedelta(days=days)))
     res = res.fetchall()

     with self.engine.begin() as conn:
       for row in res:
         logging.debug("prune: source={}, version={}".format(row["source"], row["version"]))
         conn.execute(self.inventory_table.delete().where(
               (self.inventory_table.c.source == row["source"]) &
                  (self.inventory_table.c.version == row["version"])
           ))
         conn.execute(self.source_table.delete().where(
               (self.source_table.c.source == row["source"]) &
                  (self.source_table.c.version == row["version"])
           ))
         conn.execute(self.dns_record.delete().where(
               (self.dns_record.c.source == row["source"]) &
                  (self.dns_record.c.version == row["version"])
           ))
         conn.execute(self.dns_domain.delete().where(
               (self.dns_domain.c.source == row["source"]) &
                  (self.dns_domain.c.version == row["version"])
           ))
     return True

   def disconnect(self):
     self.conn.invalidate()
     self.conn.close()
     self.conn = None
     return True
