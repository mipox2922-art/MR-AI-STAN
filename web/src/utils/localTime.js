export const TANZANIA_TIME_ZONE = "Africa/Dar_es_Salaam";

export function getHourInTimeZone(date = new Date(), timeZone = TANZANIA_TIME_ZONE) {
  const instant = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(instant.getTime())) return null;

  const hourText = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    hourCycle: "h23",
  }).format(instant);
  const hour = Number(hourText);
  return Number.isInteger(hour) && hour >= 0 && hour <= 23 ? hour : null;
}

export function getTanzaniaGreeting(date = new Date()) {
  const hour = getHourInTimeZone(date);
  if (hour === null) return "KARIBU BOSS FERISI";
  if (hour < 5) return "HABARI ZA USIKU, BOSS FERISI";
  if (hour < 12) return "HABARI ZA ASUBUHI, BOSS FERISI";
  if (hour < 16) return "HABARI ZA MCHANA, BOSS FERISI";
  if (hour < 19) return "HABARI ZA JIONI, BOSS FERISI";
  return "HABARI ZA USIKU, BOSS FERISI";
}
