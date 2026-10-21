import { useEffect, useMemo, useState } from "react";
import { dispatchTool, searchToolWeb, planAgentWork, executeMission, chat, getExecutiveBriefing, browserNavigate, browserClick, browserType, browserScroll, browserDrag, getCurrentPage, reportMissionHandoff } from "../api";
import HudOrb from "./HudOrb";
import Chat from "./Chat";
import { sanitizeAssistantMessage } from "../utils/chatSafety";
import LiveMap from "./LiveMap";
import {
  getActiveTaskForAgent,
  getTaskSummary,
  isTaskInProgress,
  taskBelongsToAgent,
} from "../utils/taskLogic";
