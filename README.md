# Docker CloudFlare DDNS

This small Python-based Docker image allows you to use the free [CloudFlare DNS Service](https://www.cloudflare.com/dns/) as a Dynamic DNS Provider ([DDNS](https://en.wikipedia.org/wiki/Dynamic_DNS)).

The application is written in Python for better stability and maintainability. This refactor was assisted by Grok Code (opencode.ai), an AI-powered coding tool.

## Usage

Quick Setup:

```shell
docker run \
  -e API_KEY=xxxxxxx \
  -e ZONE=example.com \
  -e SUBDOMAIN=subdomain \
  your-custom-image
```

## Parameters

* `--restart=always` - ensure the container restarts automatically after host reboot.
* `-e API_KEY` - Your CloudFlare scoped API token. See the [Creating a Cloudflare API token](#creating-a-cloudflare-api-token) below. **Required**
  * `API_KEY_FILE` - Path to load your CloudFlare scoped API token from (e.g. a Docker secret). *If both `API_KEY_FILE` and `API_KEY` are specified, `API_KEY_FILE` takes precedence.*
* `-e ZONE` - The DNS zone that DDNS updates should be applied to. **Required**
  * `ZONE_FILE` - Path to load your CloudFlare DNS Zone from (e.g. a Docker secret). *If both `ZONE_FILE` and `ZONE` are specified, `ZONE_FILE` takes precedence.*
* `-e SUBDOMAIN` - A subdomain of the `ZONE` to write DNS changes to. If this is not supplied the root zone will be used.
  * `SUBDOMAIN_FILE` - Path to load your CloudFlare DNS Subdomain from (e.g. a Docker secret). *If both `SUBDOMAIN_FILE` and `SUBDOMAIN` are specified, `SUBDOMAIN_FILE` takes precedence.*

## Optional Parameters

* `-e PROXIED` - Set to `true` to make traffic go through the CloudFlare CDN. Defaults to `false`.
* `-e RRTYPE=A` - Set to `AAAA` to use set IPv6 records instead of IPv4 records. Defaults to `A` for IPv4 records.
* `-e CUSTOM_LOOKUP_CMD="curl -s https://api.ipify.org"` - Set to any shell command to run and get the IP from stdout. Useful if default methods fail in your network.
* `-e DNS_SERVER=10.0.0.2` - Set to the IP address of the DNS server you would like to use. Defaults to 1.1.1.1 otherwise.

## Creating a Cloudflare API token

To create a CloudFlare API token for your DNS zone go to https://dash.cloudflare.com/profile/api-tokens and follow these steps:

1. Click Create Token
2. Provide the token a name, for example, `cloudflare-ddns`
3. Grant the token the following permissions:
    * Zone - Zone Settings - Read
    * Zone - Zone - Read
    * Zone - DNS - Edit
4. Set the zone resources to:
    * Include - All zones
5. Complete the wizard and copy the generated token into the `API_KEY` variable for the container

## IPv6 Support

If you're wanting to set IPv6 records set the environment variable `RRTYPE=AAAA`. Ensure your network supports IPv6.

## Docker Compose

If you prefer to use [Docker Compose](https://docs.docker.com/compose/):

```yml
services:
  cloudflare-ddns:
    image: your-custom-image
    restart: always
    environment:
      - API_KEY=xxxxxxx
      - ZONE=example.com
      - SUBDOMAIN=subdomain
      - PROXIED=false
```

## Acknowledgments

Thanks to oznu for the original shell-based implementation.

## License

Copyright (C) 2017-2020 oznu

Copyright (C) 2025 wy

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the [GNU General Public License](./LICENSE) for more details.
