// Tiny i18n store. English is the default and uses the original strings; Vietnamese is opt-in.
// The language itself lives on the server (shared by the whole room); useChat mirrors it here.
import { useSyncExternalStore } from "react";

let current = "en";
const listeners = new Set();

export function setLang(lang) {
  const next = lang === "vi" ? "vi" : "en";
  if (next === current) return;
  current = next;
  listeners.forEach((l) => l());
}

export function getLang() {
  return current;
}

function subscribe(l) {
  listeners.add(l);
  return () => listeners.delete(l);
}

const vi = {
  // Join modal
  "join.title": "Tham gia cuộc họp",
  "join.subtitle": "Nhập tên hiển thị của bạn để vào phòng.",
  "join.placeholder": "Tên của bạn…",
  "join.button": "Tham gia →",
  // Header
  "hdr.notInRoom": "Chưa vào phòng",
  "hdr.participants": "người trong phòng",
  "hdr.joinedAs": "Đã tham gia với tên",
  "hdr.wake": "Đánh thức máy chủ",
  "hdr.waking": "Đang đánh thức...",
  "hdr.awake": "Máy chủ đã sẵn sàng ✓",
  "hdr.pingFail": "Không kết nối được ✗",
  "hdr.pingTitle": "Gửi ping để đánh thức máy chủ khỏi chế độ ngủ của Render",
  "hdr.switchTo": "Chuyển sang chế độ",
  "hdr.full": "Đầy đủ",
  "hdr.lite": "Nhẹ",
  "hdr.silent": "Im lặng",
  "hdr.simClose": "Đóng trình mô phỏng",
  "hdr.simOpen": "Mở trình mô phỏng Người dùng 2",
  "hdr.simHide": "Ẩn trình mô phỏng",
  "hdr.simAdd": "Thêm trình mô phỏng",
  "hdr.leave": "Rời cuộc họp",
  "hdr.join": "Tham gia cuộc họp",
  "hdr.langTitle": "Chuyển sang tiếng Anh",
  // Participant cell
  "cell.you": "Bạn",
  "cell.participant": "Người tham gia",
  "cell.mute": "Tắt mic",
  "cell.unmute": "Bật mic",
  "cell.muteTitle": "Tắt mic của bạn",
  "cell.unmuteTitle": "Bật mic của bạn",
  "cell.camOff": "Tắt cam",
  "cell.camOn": "Bật cam",
  "cell.camOffTitle": "Tắt camera",
  "cell.camOnTitle": "Bật camera",
  "cell.live": "Đang mở",
  "cell.muted": "Đã tắt",
  "cell.blurOn": "Làm mờ: bật",
  "cell.blurOff": "Làm mờ: tắt",
  "cell.blurOffTitle": "Tắt làm mờ nền",
  "cell.blurOnTitle": "Bật làm mờ nền",
  "cell.empty": "Trống",
  "entropy": "Entropy",
  // Facilitator
  "fac.title": "Người điều phối AI",
  "fac.log": "Nhật ký điều phối",
  "fac.live": "TRỰC TIẾP",
  "fac.waiting": "Đang chờ phiên bắt đầu…",
  "fac.idle": "CHỜ",
  "state.idle": "Chờ",
  "state.listening": "Đang nghe",
  "state.processing": "Đang nghĩ",
  "state.speaking": "Đang nói",
  // UI overlay
  "ui.startVoice": "Bắt đầu phiên thoại",
  "ui.roomListening": "Phòng đang lắng nghe…",
  "ui.aiProcessing": "AI đang xử lý…",
  "ui.transcribing": "Đang chép lời…",
  "ui.avatarSpeaking": "Avatar đang nói…",
  "ui.turn": "🎤 Lượt hội thoại:",
  "ui.yacine": "🤖 Yacine nói:",
  "ui.room": "Phòng",
  "ui.you": " (bạn)",
  "ui.voiceSession": "Phiên thoại",
  "ui.startShared": "Bắt đầu phiên thoại chung",
  "ui.muteMy": "Tắt mic của tôi",
  "ui.unmuteMy": "Bật mic của tôi",
  "ui.zoomOut": "Thu nhỏ",
  "ui.zoomIn": "Phóng to",
  "ui.timeUp": "Hết giờ",
  "ui.timerHint": "Di chuột vào và dùng − / + để đặt thời lượng phiên (1–20 phút)",
  "ui.timerMinus": "Giảm thời lượng phiên",
  "ui.timerPlus": "Tăng thời lượng phiên",
  // Ranking board
  "rank.close": "Đóng bảng xếp hạng",
  "rank.open": "Mở bảng xếp hạng",
  "rank.closeTab": "Đóng ▸",
  "rank.openTab": "◂ Xếp hạng",
  "rank.title": "Xếp hạng sinh tồn",
  "rank.legend": "▲ quan trọng nhất  ·  ▼ ít quan trọng nhất",
  "rank.drag": "Kéo",
  "rank.dragTitle": "Kéo vào một vị trí xếp hạng hoặc về khu chưa xếp (hoặc chọn rồi nhấn Space, sau đó dùng phím mũi tên)",
  "rank.pool": "Chưa xếp hạng",
  "rank.poolHint": "Kéo từng thẻ vào vị trí xếp hạng khi hai bạn đã thống nhất",
  "rank.poolEmpty": "Đã xếp tất cả các thẻ",
  "rank.dropHere": "Thả thẻ vào đây",
  "rank.toPool": "Đưa về khu chưa xếp hạng",
  "rank.needAll": "Hãy xếp đủ các thẻ trước khi đồng ý",
  "rank.partner": "Đối tác",
  "rank.moving": "đang di chuyển…",
  "rank.bothAgreed": "✓ Cả hai đã đồng ý — xếp hạng cuối cùng",
  "rank.withdraw": "Rút lại đồng ý",
  "rank.agree": "Tôi đồng ý với thứ tự này",
  "rank.note": "Di chuyển bất kỳ thẻ nào sẽ xóa sự đồng ý của mọi người.",
  // Session summary
  "sum.title": "Tổng kết phiên",
  "sum.timeUp": "Hết giờ",
  "sum.stopped": "Phiên đã dừng",
  "sum.duration": "Thời lượng",
  "sum.turns": "Lượt hội thoại",
  "sum.facSpoke": "Yacine đã nói",
  "sum.facSilent": "Yacine im lặng",
  "sum.interruptions": "Lần ngắt lời Yacine",
  "sum.boardMoves": "Lần di chuyển thẻ",
  "sum.times": "lần",
  "sum.participants": "Người tham gia",
  "sum.words": "từ",
  "sum.utterances": "lượt nói",
  "sum.speaking": "thời gian nói",
  "sum.metrics": "Chỉ số",
  "sum.balance": "Độ lệch cân bằng hội thoại (D)",
  "sum.balanceHint": "Càng thấp càng cân bằng",
  "sum.deadlocks": "Số lần im lặng kéo dài",
  "sum.deadlocksHint": "≥ 4 giây không ai nói",
  "sum.rankScore": "Độ lệch xếp hạng cuối",
  "sum.rankHint": "Càng thấp càng gần xếp hạng Coast Guard",
  "sum.finalRanking": "Xếp hạng cuối của nhóm",
  "sum.pair": "Nhóm",
  "sum.expert": "Chuẩn",
  "sum.agreed": "Cả hai đã đồng ý",
  "sum.notAgreed": "Chưa cùng đồng ý",
  "sum.unplaced": "chưa xếp",
  "sum.incomplete": "thẻ chưa được xếp (tính theo trường hợp xấu nhất)",
  "sum.facActions": "Hành động của người điều phối",
  "sum.download": "Tải dữ liệu (JSON)",
  "sum.close": "Đóng",

  // Admin observer
  "admin.title": "Quản trị · đang quan sát (ẩn)",
  "admin.badge": "Quản trị viên quan sát (ẩn)",
  "admin.status": "Phiên",
  "admin.running": "đang chạy",
  "admin.idle": "chưa chạy",
  "admin.participants": "Người tham gia",
  "admin.sessions": "Các phiên đã kết thúc",
  "admin.downloadAll": "Tải tất cả",
  "admin.noSessions": "Chưa có phiên nào kết thúc. Dữ liệu sẽ xuất hiện ở đây khi phiên kết thúc.",
  "admin.downloaded": "đã tải",
  "admin.notDownloaded": "chưa tải",
  "admin.score": "điểm",
  "admin.downloadCsv": "Tải CSV",
  "admin.boardReadOnly": "Chế độ quản trị — chỉ xem",
  "admin.guardTitle": "Dữ liệu phiên chưa được tải",
  "admin.guardBody": "Các phiên này chưa được tải về. Dữ liệu không được lưu ở nơi nào khác — nếu rời đi bây giờ, dữ liệu sẽ bị mất.",
  "admin.downloadAllLeave": "Tải tất cả & rời đi",
  "admin.leaveAnyway": "Rời đi không tải (dữ liệu sẽ bị mất)",
  "admin.cancel": "Hủy — ở lại",
  "sum.na": "—",
};

// The 15 "Lost at Sea" card names, by ORIGINAL board item id (item-1 … item-15). The board currently uses only 6 of them (see back/app/services/scenario.py).
const itemsVi = [
  "Kính lục phân (sextant)",
  "Gương cạo râu",
  "Màn chống muỗi",
  "Thùng nước 25 lít",
  "Một thùng lương khô quân đội",
  "Bản đồ Thái Bình Dương",
  "Phao cứu sinh",
  "Can hỗn hợp dầu/xăng 10 lít",
  "Radio bán dẫn nhỏ",
  "Tấm nhựa đục 20 feet vuông",
  "Một lọ thuốc đuổi cá mập",
  "Một chai cồn y tế",
  "Dây nylon 15 feet",
  "2 hộp sô-cô-la",
  "Bộ cần câu cá biển",
];

const actionsVi = {
  NO_ACTION: "IM LẶNG",
  DEEPEN: "ĐÀO SÂU",
  RESOLVE: "GIẢI QUYẾT",
  NEXT_ITEM: "MỤC TIẾP",
  CLARIFY: "LÀM RÕ",
  REDIRECT: "QUAY LẠI",
  ENCOURAGE: "KHUYẾN KHÍCH",
  SUMMARIZE: "TÓM TẮT",
  MEDIATE: "HÒA GIẢI",
  INTERVENE: "CAN THIỆP",
  LITE: "NHẸ",
  OPEN: "MỞ ĐẦU",
  NUDGE: "GỢI MỞ",
  TIME_CHECK: "THỜI GIAN",
  WRAP_UP: "KẾT THÚC",
  UNKNOWN: "KHÁC",
};

/** Translate a key. English callers pass the original string as `en`, so English is untouched. */
export function tr(lang, key, en) {
  return lang === "vi" ? (vi[key] ?? en) : en;
}

export function useLang() {
  return useSyncExternalStore(subscribe, getLang, getLang);
}

/** Returns t(key, englishText). */
export function useT() {
  const lang = useLang();
  return (key, en) => tr(lang, key, en);
}

/** Board card label: Vietnamese name for item-N when in Vietnamese, otherwise the server label. */
export function itemLabel(lang, id, fallback) {
  if (lang !== "vi") return fallback;
  const m = /^item-(\d+)$/.exec(id);
  return (m && itemsVi[Number(m[1]) - 1]) || fallback;
}

export function actionLabel(lang, action) {
  return lang === "vi" ? (actionsVi[action] ?? action) : action;
}
