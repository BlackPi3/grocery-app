#!/bin/sh
# Email alerts for unusual activity, in Cloud Monitoring (Parham, 2026-10-12:
# guests and a second user are in, "we don't want to bleed money without
# knowing"). Run once; running it again changes nothing.
#
#   GROCERY_PROJECT=<gcp project id> GROCERY_ALERT_EMAIL=<address> scripts/setup-alerts.sh
#
# Two alerts, on both servers (the real one and the demo):
# - Spending: the server logs SPEND_ALERT when a day's model calls pass
#   another dollar (grocery_app/spend.py); any such line is an email.
# - Traffic: more than 2,000 requests to one server in an hour. The page asks
#   every 3 s while a receipt is read (about 1,200 an hour), so ordinary use
#   stays below it.
# Google's billing budget (Console -> Billing -> Budgets & alerts) is the
# backstop for everything else on the bill; only the account owner can set it.
set -eu

PROJECT=${GROCERY_PROJECT:?set GROCERY_PROJECT to the Google Cloud project id}
EMAIL=${GROCERY_ALERT_EMAIL:?set GROCERY_ALERT_EMAIL to where alerts go}

channel=$(gcloud beta monitoring channels list --project "$PROJECT" \
  --filter="labels.email_address=\"$EMAIL\"" --format='value(name)' | head -n 1)
if [ -z "$channel" ]; then
  channel=$(gcloud beta monitoring channels create --project "$PROJECT" \
    --display-name "Grocery alerts: $EMAIL" --type email \
    --channel-labels "email_address=$EMAIL" --format='value(name)')
fi

existing=$(gcloud alpha monitoring policies list --project "$PROJECT" --format='value(displayName)')
policy() {  # name, then the policy as JSON on stdin
  if printf '%s\n' "$existing" | grep -qx "$1"; then
    echo "already there: $1"
    cat >/dev/null
    return
  fi
  file=$(mktemp)
  cat >"$file"
  gcloud alpha monitoring policies create --project "$PROJECT" --policy-from-file "$file" \
    --format='value(name)'
  rm -f "$file"
}

policy "Grocery: unusual model spending" <<EOF
{
  "displayName": "Grocery: unusual model spending",
  "documentation": {"content": "A server's model calls passed another dollar today (UTC). The log line says how much and what the last call was for. Normal days cost cents: look at the Costs card on the You tab, or the model_calls table.", "mimeType": "text/markdown"},
  "combiner": "OR",
  "conditions": [{
    "displayName": "SPEND_ALERT in a server's log",
    "conditionMatchedLog": {
      "filter": "resource.type=\"cloud_run_revision\" AND textPayload:\"SPEND_ALERT\""
    }
  }],
  "alertStrategy": {"notificationRateLimit": {"period": "3600s"}, "autoClose": "86400s"},
  "notificationChannels": ["$channel"]
}
EOF

policy "Grocery: unusual traffic" <<EOF
{
  "displayName": "Grocery: unusual traffic",
  "documentation": {"content": "One server answered more than 2,000 requests in an hour. Ordinary use stays well below; look at the service's logs in Cloud Run for who is asking.", "mimeType": "text/markdown"},
  "combiner": "OR",
  "conditions": [{
    "displayName": "Requests per hour, per server",
    "conditionThreshold": {
      "filter": "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\"",
      "aggregations": [{
        "alignmentPeriod": "3600s",
        "perSeriesAligner": "ALIGN_SUM",
        "crossSeriesReducer": "REDUCE_SUM",
        "groupByFields": ["resource.label.service_name"]
      }],
      "comparison": "COMPARISON_GT",
      "thresholdValue": 2000,
      "duration": "0s"
    }
  }],
  "alertStrategy": {"autoClose": "86400s"},
  "notificationChannels": ["$channel"]
}
EOF
