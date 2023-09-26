#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import quart
import yaml
import asfpy.sqlite
import migrate
import random
import string
import time

app = quart.Quart(__name__)
config = yaml.safe_load(open("config.yaml"))
db = asfpy.sqlite.db(config["db"])
url_cache = {}


def random_id(length=5):
    """Generates a random shortlink ID"""
    letters = string.ascii_lowercase + string.digits
    return "".join(random.choice(letters) for _i in range(length))


@app.route("/")
async def frontpage():
    """This is just the index.html file..."""
    return await quart.send_file("index.html")


@app.errorhandler(404)
async def find_short_link(_err):
    """Tries to find a shortened URL and redirect to the origin"""
    uid = quart.request.path[1:]
    url_suffix = ""
    if "/" in uid:  # s.apache.org/someid/suffix -> origin.url/bla/suffix
        uid, url_suffix = uid.split("/", maxsplit=1)
    if uid in url_cache:
        origin = url_cache[uid]["url"]
        if url_suffix:  # Strip trailing slash if needed, then add one, and then the suffix
            origin = origin.rstrip("/") + "/" + url_suffix
        return quart.Response(response=f"{origin}\n", status=302, headers={"Location": origin})
    # No such short link? 404!
    return quart.Response(response=f"No such short link: {uid}\n", status=404, headers={"Content-Type": "text/plain"})


@app.route(
    "/s/new",
    methods=[
        "POST",
    ],
)
async def store_url():
    """Endpoint for storing URLs"""
    postdata = await quart.request.form
    link_id = postdata.get("uid")
    url = postdata.get("url")
    override = postdata.get("override")
    whoami = quart.request.headers.get("X-Authenticated-User")
    if not whoami:
        return "Please authenticate!", 403

    # Validate URL
    if any(char in url for char in string.whitespace) or ":" not in url:
        return quart.Response(
            response=f"The provided URL is not a valid URL\n",
            status=400,
            headers={"Content-Type": "text/plain"},
        )

    # Validate link id if set
    if link_id:
        if link_id in url_cache:
            original_owner = url_cache[link_id]["owner"]
            if (whoami not in config["admins"] and original_owner != whoami) or override != "yes":
                return (
                    f"A short link with the ID '{link_id}' already exists. The original owner ({original_owner}) or Infra can override this link by ticking the override box.\n",
                    403,
                    {"Content-Type": "text/plain"},
                )

        elif any(char not in config["valid_id_characters"] for char in link_id):
            return (
                f"The provided link ID contains characters that are not allowed.\n",
                400,
                {"Content-Type": "text/plain"},
            )

    # If no preferred link ID, make one up
    if not link_id:
        link_id = random_id()
        while link_id in url_cache:
            link_id = random_id()

    # Store the link with an upsert
    new_record = {
        "id": link_id,
        "url": url,
        "owner": whoami,
        "created": int(time.time()),
    }
    db.upsert("shortlinks", new_record, id=link_id)
    url_cache[link_id] = new_record

    # Report success
    return f"Short link created: https://s.apache.org/{link_id}\n"


@app.route("/s/private")
async def list_urls():
    """Endpoint for listing URLs that $user has made"""
    whoami = quart.request.headers.get("X-Authenticated-User")
    if not whoami:
        return "Please authenticate!", 403
    action = quart.request.args.get("action")
    if action == "list":
        if quart.request.args.get("raw"):  # Raw text response
            link_list = "\n".join(
                [f"{linkid} -> {record['url']}" for linkid, record in url_cache.items() if record["owner"] == whoami]
            )
            return link_list, 200, {"Content-Type": "text/plain"}
        else:  # JSON response
            link_list = {linkid: record["url"] for linkid, record in url_cache.items() if record["owner"] == whoami}
            if link_list:
                return link_list
            return "No links found"
    return "No known action requested"


if __name__ == "__main__":
    # Make sure the shortlinks table exists
    if not db.table_exists("shortlinks"):
        db.runc(migrate.DB_CREATE_STATEMENT)

    # Load stored URLs into memory
    for record in db.fetch("shortlinks", limit=0):
        url_cache[record["id"]] = record

    # Run the server
    app.run(port=config["port"])
