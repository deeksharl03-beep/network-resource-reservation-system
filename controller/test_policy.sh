#!/bin/bash
URL=http://127.0.0.1:8080
H='Content-Type: application/json'
post() { curl -s -w "  -> HTTP %{http_code}\n" -X POST $URL/policy -H "$H" -d "$1"; }

GOOD='{"id":1,"src_ip":"10.0.0.1","dst_ip":"10.0.0.3","rate_kbps":20000,"hops":[{"dpid":1,"in_port":1,"out_port":3},{"dpid":2,"in_port":1,"out_port":2},{"dpid":4,"in_port":3,"out_port":1}]}'
BADDPID='{"id":2,"src_ip":"10.0.0.1","dst_ip":"10.0.0.3","rate_kbps":20000,"hops":[{"dpid":9,"in_port":1,"out_port":3}]}'
OVER='{"id":3,"src_ip":"10.0.0.1","dst_ip":"10.0.0.3","rate_kbps":120000,"hops":[{"dpid":1,"in_port":1,"out_port":3},{"dpid":2,"in_port":1,"out_port":2},{"dpid":4,"in_port":3,"out_port":1}]}'

echo "1. valid policy (expect 200)";   post "$GOOD"
echo "2. duplicate id (expect 409)";   post "$GOOD"
echo "3. unknown dpid (expect 400)";   post "$BADDPID"
echo "4. over capacity (expect 409)";  post "$OVER"
echo "5. invalid JSON (expect 400)";   post "not json"
echo "6. list policies";               curl -s $URL/policy; echo
echo "7. delete (expect 200)";         curl -s -w "  -> HTTP %{http_code}\n" -X DELETE $URL/policy/1
echo "8. delete again (expect 404)";   curl -s -w "  -> HTTP %{http_code}\n" -X DELETE $URL/policy/1
