export interface StageInfo {
  id: string;
  title: string;
  turns: number;
  status: string;
}

export interface ProfileInfo {
  name: string | null;
  role: string | null;
  photo: string | null;
  photoUrl: string | null;
}

export interface PanelData {
  stages: StageInfo[];
  currentStageId: string;
  completedStageIds: string[];
  profile: ProfileInfo;
}

export interface SessionState {
  sessionId: string;
  panelData: PanelData;
  messages: { role: string; content: string }[];
  turnCount: number;
}

// --- Card / profile types ---

export interface SkillCardProfile {
  name: string;
  title: string;
  industry: string;
  strengths: string[];
  clifton_strengths: string[];
  inspirations: string[];
  aspirations: string[];
  learn_grow: string[];
  accomplishments: string[];
  growth_focus: string;
  flavor_text: string;
}

export type CardData = SkillCardProfile;

// --- Client-side session model (localStorage) ---

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface CompletedStage {
  id: string;
  title: string;
  summary: string;
  turnCount: number;
}

export interface Identity {
  name: string | null;
  role: string | null;
  title: string | null;
  photoStatus: 'unknown' | 'uploaded' | 'skipped';
}

export interface CardStyle {
  stylePreset: string | null;
  personaSetting: string | null;
  accentColor: string | null;
}

export const EMPTY_CARD_STYLE: CardStyle = {
  stylePreset: null,
  personaSetting: null,
  accentColor: null,
};

export interface ClientSession {
  sessionId: string;
  currentStageId: string;
  completedStages: CompletedStage[];
  currentStageMessages: ChatMessage[];
  identity: Identity;
  photoBase64: string | null;
  cliftonStrengths: string[];
  panelData: PanelData;
  cardData: CardData | null;
  style: CardStyle;
  createdAt: string;
}

export interface StateUpdate {
  currentStageId: string;
  identity: Identity;
  stageAdvanced: boolean;
  stageSummary: string | null;
  panelData: PanelData;
}
