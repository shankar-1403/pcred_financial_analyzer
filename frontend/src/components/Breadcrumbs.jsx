import { Link } from "react-router-dom";
import { IconChevronRight } from "@tabler/icons-react";

export default function Breadcrumbs({ items }) {
  return (
    <div className="flex items-center text-xl font-semibold">
      {items.map((item, index) => (
        <div key={index} className="flex items-center">
          
          {item.path ? (
            <Link
              to={item.path}
              className="hover:underline text-blue-700 text-base"
            >
              {item.label}
            </Link>
          ) : (
            <span className="text-base text-[#084b6f]">{item.label}</span>
          )}

          {index !== items.length - 1 && (
            <span className="mx-1 mt-1 text-[#084b6f]"><IconChevronRight size={16}/></span>
          )}

        </div>
      ))}
    </div>
  );
}