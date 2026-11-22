"use client";

import { useEffect, useState } from "react";
import { ImageOff, Loader2 } from "lucide-react";
import { LoiTaiAnh, getPhotoVerificationImage } from "@/lib/doses";

// Anh xac minh la PHI: tai qua fetch kem JWT roi hien bang object URL (giong
// app/doctor/reviews/[id]), khong dung <img src> truc tiep vi khong gan duoc
// header Authorization.
export function PhotoVerificationImage({
  verificationId,
  alt,
  className,
}: {
  verificationId: string;
  alt: string;
  className?: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  // null = chua loi. Phan biet 404 (anh khong con) voi het phien/khong co
  // quyen/loi mang - noi nham "anh khong con" khien nguoi than duyet lieu ma
  // khong thay bang chung.
  const [loi, setLoi] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    setUrl(null);
    setLoi(null);
    getPhotoVerificationImage(verificationId)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (active) setUrl(objectUrl);
        else URL.revokeObjectURL(objectUrl);
      })
      .catch((err: unknown) => {
        if (!active) return;
        const status = err instanceof LoiTaiAnh ? err.status : 0;
        setLoi(
          status === 404
            ? "Ảnh không còn trên máy chủ."
            : status === 401 || status === 403
              ? "Không tải được ảnh: phiên đăng nhập đã hết hoặc bạn không có quyền xem. Hãy tải lại trang hoặc đăng nhập lại."
              : "Không tải được ảnh. Vui lòng kiểm tra kết nối rồi thử lại.",
        );
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [verificationId]);

  if (loi) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-muted p-3 text-xs text-muted-foreground">
        <ImageOff className="h-4 w-4 shrink-0" /> {loi}
      </div>
    );
  }
  if (!url) {
    return (
      <div className="flex items-center gap-2 p-3 text-xs text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Đang tải ảnh…
      </div>
    );
  }
  return <img src={url} alt={alt} className={className} />;
}
