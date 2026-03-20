"use client";

import React, { useState } from "react";
import { Navbar, NavBody, NavItems, NavbarLogo, MobileNav, MobileNavHeader, MobileNavMenu, MobileNavToggle} from "../components/resizable-navbar";
import { IconCaretDownFilled,IconUser, IconShield } from "@tabler/icons-react";
import { Link } from "react-router-dom";
import { motion as Motion, AnimatePresence } from "motion/react";
import { useNavigate } from "react-router-dom";

const navItems = [
  { name: "Home", link: "/" },
  { name: "Reports", link: "/reports" },
  { name: "Masters", 
    children: [
      { name: "Users", link: "/master/users" },
      { name: "Roles", link: "/master/roles" },
    ]
  },
  { name: "Manage Subscription", link: "/" },
  { name: "API Documentation", link: "/" },
];

const mobNavItems = [
  { name: "Home", link: "/" },
  { name: "Reports", link: "/" },
  { name: "Masters", 
    children: [
      { name: "Users", link: "/master/users" },
      { name: "Roles", link: "/master/roles" },
    ]
  },
  { name: "Manage Subscription", link: "/" },
  { name: "API Documentation", link: "/" },
];
 
export default function Header() {
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false);
  const [open, setOpen] = useState(false);
  const [productsOpen, setProductsOpen] = useState(false);
  const handleLogout = () => {
    localStorage.removeItem("name");
    localStorage.removeItem("auth");
    localStorage.removeItem("session_token");
    navigate("/")
  }

  const email_id = localStorage.getItem("auth");
  return (
    <>
      <Navbar>
        <NavBody>
          <div className="flex items-center gap-10">
            <NavbarLogo />
            <NavItems items={navItems} />
          </div>
          <div className="flex items-center z-60">
            <button onClick={() => setOpen(open == true ? false : true)} className="relative overflow-hidden p-2 bg-[#E18126] rounded-full group transition-colors duration-300 cursor-pointer flex items-center gap-3">
              <span className="relative z-10 text-white"><IconUser/></span>
            </button>
            <AnimatePresence>
              {open == true && 
                <Motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="absolute top-full mt-2 -right-30 w-60 -translate-x-1/2 rounded-xl bg-white shadow-xl overflow-hidden"
                >   
                  <div className="block px-4 py-2 text-sm font-semibold text-blue-950">
                    <p>{email_id}</p>
                  </div>
                  <Link to={"/"} className="block text-start px-4 py-2 text-base hover:bg-neutral-100 hover:text-[#E18126] text-blue-950 font-semibold">Change Password</Link>
                  <button onClick={handleLogout} className="block text-start px-4 py-2 text-base hover:bg-neutral-100 hover:text-[#E18126] text-red-600 font-bold w-full cursor-pointer">Logout</button>
                </Motion.div>
              }
            </AnimatePresence>
          </div>
        </NavBody>
      </Navbar>
      {/* Mobile Navbar */}
      <MobileNav>
        <MobileNavHeader>
          <NavbarLogo />
          <MobileNavToggle
            isOpen={isOpen}
            onClick={() => setIsOpen(!isOpen)}
          />
        </MobileNavHeader>

        <MobileNavMenu isOpen={isOpen} onClose={() => setIsOpen(false)}>
          {mobNavItems.map((item) => {
            if (item.children) {
              return (
                <>
                  <button onClick={() => setProductsOpen(!productsOpen)} className="text-blue-950 font-bold text-left flex justify-between items-center w-full">{item.name}<IconCaretDownFilled className="w-4 h-4" color="#162556"/></button>
                  {productsOpen && (
                    <div className="flex flex-col space-y-4">
                      {item.children.map((child) => (
                        <Link
                          key={child.name}
                          href={child.link}
                          onClick={() => {
                            setIsOpen(false);
                            setProductsOpen(false);
                          }}
                          className="text-blue-950 text-base font-bold flex gap-2 items-center"
                        ><IconShield className="w-4 h-4" color="#E18126"/>{child.name}
                        </Link>
                      ))}
                    </div>
                  )}
                </>
              );
            }

            return (
              <Link
                key={item.name}
                href={item.link}
                onClick={() => setIsOpen(false)}
                className="text-blue-950 text-base font-bold"
              >
                {item.name}
              </Link>
            );
          })}
        </MobileNavMenu>
      </MobileNav>
    </>
  );
}
