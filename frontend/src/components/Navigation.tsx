"use client";

import React, { useState } from "react";
import AppSidebar from "@/components/layout/AppSidebar";

export default function Navigation() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <AppSidebar
      isMobileOpen={mobileOpen}
      onCloseMobile={() => setMobileOpen(false)}
    />
  );
}
