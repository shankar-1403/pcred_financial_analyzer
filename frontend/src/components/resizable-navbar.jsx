import { IconMenuDeep, IconX } from "@tabler/icons-react";
// eslint-disable-next-line no-unused-vars
import { motion, AnimatePresence, useScroll, useMotionValueEvent } from "framer-motion";
import React, { useRef, useState } from "react";
import { Link } from "react-router-dom";
import {IconCaretDownFilled} from "@tabler/icons-react";
import { cn } from "../lib/utils";

export const Navbar = ({ children, className }) => {
  const ref = useRef(null);
  const { scrollY } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const [visible, setVisible] = useState(false);

  useMotionValueEvent(scrollY, "change", (latest) => {
    if (latest > 100) {
      setVisible(true);
    } else {
      setVisible(false);
    }
  });

  return (
    <motion.div
      ref={ref}
      className={cn(`fixed top-0 inset-x-0 z-60 w-full transition-all duration-300 ease-out bg-[#084b6f] shadow-lg`, className)}
    >
      {React.Children.map(children, (child) =>
        React.isValidElement(child)
          ? React.cloneElement(
              child,
              { visible },
            )
          : child,
      )}
    </motion.div>
  );
};

export const NavBody = ({ children }) => {
  return (
    <div className="relative flex-row items-center justify-between self-start mx-10 py-2 lg:flex">
      {children}
    </div>
  );
};

export const NavItems = ({ items }) => {
  const [open, setOpen] = useState(null);
 
  return (
    <div className="relative hidden lg:flex items-center justify-start gap-8 -mt-1">
      {items.map((item, idx) => (
        <div
          key={item.name}
          onClick={() => setOpen(open == null ? idx : null)}
        >
          {item.link ? (
              <Link to={item.link} className="text-sm text-white cursor-pointer">{item.name}</Link>
          ) : (
            <span className={`text-sm text-white cursor-pointer flex items-center gap-1`}>
              <div className="cursor-pointer text-left text-sm py-3 flex gap-2 items-center">
                  <span>{item.name}</span>
                  <div>
                  <IconCaretDownFilled className="w-3 h-3" />
                  </div>
              </div>
            </span>
          )}
          {/* Dropdown */}
          <AnimatePresence>
            {item.children && open === idx && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                className="absolute left-2/5 top-full mt-1 w-40 -translate-x-1/2 rounded-lg bg-white shadow-xl overflow-hidden"
              >
                {item.children.map((child) => (
                  <Link
                    key={child.name}
                    to={child.link}
                    className="block px-4 py-3 text-sm hover:bg-neutral-100 hover:text-[#E18126] text-[#084b6f] font-bold"
                  >
                    {child.name}
                  </Link>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      ))}
    </div>
  );
};

export const MobileNav = ({ children, className }) => {
  return (
    <motion.div
      className={cn(`z-50 flex w-full top-2 md:top-5 flex-col items-center justify-between px-0 py-2 fixed lg:hidden `, className )}
    >
      {children}
    </motion.div>
  );
};

export const MobileNavHeader = ({
  children,
}) => {
  const ref = useRef(null);
  const { scrollY } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const [visible, setVisible] = useState(false);

  useMotionValueEvent(scrollY, "change", (latest) => {
    if (latest > 100) {
      setVisible(true);
    } else {
      setVisible(false);
    }
  });
  return (
    <div ref={ref} className="w-full px-2 md:px-0">
      <div
        className={`flex w-full md:max-w-165 md:mx-auto flex-row items-center justify-between px-2 ${visible ? "bg-white/80 border-white backdrop-blur-md shadow-lg" : "border-transparent"} rounded-full`}
      >
        {children}
      </div>
    </div>
  );
};

export const MobileNavMenu = ({
  children,
  className,
  isOpen,
}) => {
  return (
    <AnimatePresence>
      {isOpen && (
        <div className="absolute inset-x-0 px-2 md:px-0 top-24 md:top-34">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={cn(
              "z-50 flex w-full flex-col items-start justify-start gap-4 bg-white/80 backdrop-blur-md px-4 py-8 shadow-[0_0_24px_rgba(34,42,53,0.06),0_1px_1px_rgba(0,0,0,0.05),0_0_0_1px_rgba(34,42,53,0.04),0_0_4px_rgba(34,42,53,0.08),0_16px_68px_rgba(47,48,55,0.05),0_1px_0_rgba(255,255,255,0.1)_inset] rounded-4xl md:max-w-165 mx-auto",
              className,
            )}
          >
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export const MobileNavToggle = ({
  isOpen,
  onClick,
}) => {
  return isOpen ? (
    <div className="px-6">
      <IconX className="text-[#E18126]" onClick={onClick} />
    </div>
  ) : (
    <div className="px-6">
      <IconMenuDeep className="w-7 md:w-8 h-7 md:h-8" color="#E18126" onClick={onClick} />
    </div>
  );
};

export const NavbarLogo = () => {

  return (
    <Link to="/" className="z-20">
      <img src={'/src/assets/mini_logo.webp'} alt="PCRED" className="h-12"/>
    </Link>
  )
};