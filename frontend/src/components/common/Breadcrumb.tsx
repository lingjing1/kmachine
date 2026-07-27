import { Link } from 'react-router-dom';

interface BreadcrumbPath {
  name: string;
  path?: string;
}

interface BreadcrumbProps {
  paths: BreadcrumbPath[];
}

function Breadcrumb({ paths }: BreadcrumbProps) {
  return (
    <nav className="mb-0">
      <ol className="list-none p-0 m-0 flex items-center gap-2 text-sm">
        {paths.map((path, index) => (
          <li key={index} className="flex items-center">
            {path.path ? (
              <Link
                to={path.path}
                className="text-gray-600 no-underline transition-colors hover:text-blue-600 hover:underline"
              >
                {path.name}
              </Link>
            ) : (
              <span className="text-blue-700 font-bold">{path.name}</span>
            )}
            {index < paths.length - 1 && (
              <span className="ml-2 text-neutral-text-light">/</span>
            )}
          </li>
        ))}
      </ol>
    </nav >
  );
}

export default Breadcrumb;