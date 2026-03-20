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

export interface CardExpertise {
  label: string;
  score: number;
}

export interface CardData {
  display_name: string;
  card_title: string;
  level: number;
  xp: number;
  top_expertise: CardExpertise[];
  people_i_admire: string[];
  technical_accomplishments: string[];
  influential_ideas: string[];
  strategic_curiosities: string[];
  grow_into: string;
  xp_to_next_level: number;
  flavor_text: string;
}
