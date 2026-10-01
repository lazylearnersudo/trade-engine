"""Add HTTPS ingress while retaining all existing security-list rules."""

import json
import urllib.request

import oci

request = urllib.request.Request(
    "http://169.254.169.254/opc/v2/instance/", headers={"Authorization": "Bearer Oracle"}
)
instance = json.load(urllib.request.urlopen(request, timeout=5))
try:
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    compute = oci.core.ComputeClient({}, signer=signer)
    network = oci.core.VirtualNetworkClient({}, signer=signer)
    attachments = compute.list_vnic_attachments(
        instance["compartmentId"], instance_id=instance["id"]
    ).data
    vnic = network.get_vnic(attachments[0].vnic_id).data
    subnet = network.get_subnet(vnic.subnet_id).data
    for identity in subnet.security_list_ids:
        response = network.get_security_list(identity)
        current = response.data
        rules = list(current.ingress_security_rules)
        already_allowed = any(
            rule.protocol == "6"
            and rule.source == "0.0.0.0/0"
            and (
                rule.tcp_options is None
                or rule.tcp_options.destination_port_range is None
                or rule.tcp_options.destination_port_range.min
                <= 443
                <= rule.tcp_options.destination_port_range.max
            )
            for rule in rules
        )
        if not already_allowed:
            rules.append(
                oci.core.models.IngressSecurityRule(
                    protocol="6",
                    source="0.0.0.0/0",
                    source_type="CIDR_BLOCK",
                    is_stateless=False,
                    description="Trade Engine HTTPS",
                    tcp_options=oci.core.models.TcpOptions(
                        destination_port_range=oci.core.models.PortRange(min=443, max=443)
                    ),
                )
            )
            network.update_security_list(
                identity,
                oci.core.models.UpdateSecurityListDetails(
                    ingress_security_rules=rules,
                    egress_security_rules=current.egress_security_rules,
                ),
                if_match=response.headers.get("etag"),
            )
    print("HTTPS ingress verified or added using instance-principal permissions.")
except oci.exceptions.ServiceError as error:
    print("OCI IAM access unavailable:", error.status, error.code)
except Exception as error:
    print("Instance-principal access unavailable:", type(error).__name__)
