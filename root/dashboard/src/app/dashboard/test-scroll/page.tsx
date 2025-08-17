'use client';

export default function TestScrollPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Test Scroll Page</h1>
      
      {/* Generate many cards to test scroll */}
      {Array.from({ length: 50 }, (_, i) => (
        <div key={i} className="p-6 bg-white border rounded-lg shadow">
          <h2 className="text-xl font-semibold">Card {i + 1}</h2>
          <p className="text-gray-600 mt-2">
            This is card number {i + 1}. This page should be scrollable if there are enough cards.
            Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor 
            incididunt ut labore et dolore magna aliqua.
          </p>
        </div>
      ))}
    </div>
  );
}
