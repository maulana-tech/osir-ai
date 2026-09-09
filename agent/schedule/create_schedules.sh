#!/usr/bin/env bash
# Create the three EventBridge Scheduler schedules that drive the agent on AgentCore Runtime.
#
# Usage: AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:...:runtime/osir-xyz \
#        SCHEDULER_ROLE_ARN=arn:aws:iam::123456789012:role/osir-scheduler \
#        ./create_schedules.sh
#
# The role needs bedrock-agentcore:InvokeAgentRuntime on the runtime ARN and a trust policy
# for scheduler.amazonaws.com. The schedules call InvokeAgentRuntime directly through a
# universal target, so there is no Lambda in between.
set -euo pipefail

: "${AGENT_RUNTIME_ARN:?set AGENT_RUNTIME_ARN}"
: "${SCHEDULER_ROLE_ARN:?set SCHEDULER_ROLE_ARN}"
GROUP="${SCHEDULE_GROUP:-osir-agent}"

aws scheduler create-schedule-group --name "$GROUP" >/dev/null 2>&1 || true

create() {
  local name="$1" expr="$2" task="$3"
  local payload session
  payload=$(printf '{"task":"%s"}' "$task")
  session="osir-${task}-$(date +%s)-schedule-session-000000000"   # runtimeSessionId must be 33+ chars
  local input
  input=$(jq -cn --arg arn "$AGENT_RUNTIME_ARN" --arg p "$payload" --arg s "$session" \
    '{agentRuntimeArn:$arn, qualifier:"DEFAULT", runtimeSessionId:$s, payload:$p}')
  aws scheduler create-schedule \
    --name "$name" --group-name "$GROUP" \
    --schedule-expression "$expr" \
    --flexible-time-window '{"Mode":"FLEXIBLE","MaximumWindowInMinutes":5}' \
    --target "$(jq -cn --arg role "$SCHEDULER_ROLE_ARN" --arg input "$input" \
      '{RoleArn:$role, Arn:"arn:aws:scheduler:::aws-sdk:bedrockagentcore:invokeAgentRuntime", Input:$input}')"
  echo "created $name ($expr → task=$task)"
}

create osir-inbox    "rate(15 minutes)"          inbox
create osir-calendar "cron(0 7 * * ? *)"          calendar   # daily 07:00 UTC
create osir-digest   "cron(0 8 ? * MON *)"        digest     # Mondays 08:00 UTC
