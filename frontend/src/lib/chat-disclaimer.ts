// Cau luu y ve thong tin thuoc. Backend van gan nguyen van cau nay vao cuoi
// cau tra loi (TASK-023, backend/agents/v2/orchestrator.py::_DRUG_INFO_DISCLAIMER)
// de API, audit va judge giu nguyen hop dong. Giao dien chat thi hien no MOT
// lan, co dinh duoi o nhap, nen bo cau nay khoi tung bong bong (ca lich su da
// luu) va khoi phan doc to bang giong noi.

export const DRUG_INFO_DISCLAIMER =
  "Thông tin này chỉ mang tính tham khảo, không thay thế tư vấn của bác sĩ hoặc dược sĩ.";

export function stripDrugInfoDisclaimer(text: string): string {
  if (!text.includes(DRUG_INFO_DISCLAIMER)) return text;
  return text.split(DRUG_INFO_DISCLAIMER).join("").replace(/\n{3,}/g, "\n\n").trim();
}
