//@ts-nocheck
import { useState, useEffect } from 'react'
import viteLogo from '/vite.svg'
import './App.css'
import { Selection, DetailsList, Stack, IStackTokens, DefaultButton, PrimaryButton, TextField, Spinner, SpinnerSize } from "@fluentui/react"
import Markdown from "react-markdown"

const smallTokens: IStackTokens = { childrenGap: 's1', padding: 's1' };
function App() {
  const [patientLikes, setPatientLikes] = useState<string>('');
  const [patientDislikes, setPatientDislikes] = useState<string>('');
  const [patientAllergies, setPatientAllergies] = useState<string>('');
  const [update, setUpdate] = useState<string>('');
  const [step, setStep] = useState<number>(1);
  const [response, setResponse] = useState<string>('');
  const [initialRes, setInitialRes] = useState<boolean>(false); 
  const [loading, setLoading] = useState<boolean>(false);
  const [items, setItems] = useState([]);
  const columns = [
    { key: "category", name: "Category", fieldName: "category", minWidth: 100, maxWidth: 200 },
    { key: "food", name: "Food Combinations", fieldName: "food", minWidth: 100, maxWidth: 250 },
    { key: "goal", name: "Goal", fieldName: "goal", minWidth: 150, maxWidth: 400 },
  ];

  const emptySelection = new Selection({
    onSelectionChanged: () => { },
    items: [],
  });


  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch('http://localhost:7071/api/create_message2', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          patient_likes: patientLikes,
          patient_dislikes: patientDislikes,
          patient_restrictions: patientAllergies,
          initial_request: true
        }),
      });
      const data = await res.json();
      console.log(data);
      setInitialRes(true);
      setResponse(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch('http://localhost:7071/api/create_message2', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          update: update,
        }),
      });
      const data = await res.json();
      setResponse(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    console.log(response);
    if (response) {
      const tempItems = response.recommendations.flatMap((recommendation) =>
        recommendation.foods.map((food) => ({
          category: recommendation.category,
          food: `${food.food} + ${food.ingredients.join(' + ')}`,
          goal: food.goal,
        }))
      );
      setItems(tempItems);
    }
  }, [response])

  return (
    <div>
      <img src={viteLogo} className="logo" alt="Vite logo" />
      <h1>ARFID Assistant</h1>
      <p>This tool is meant to assist medical professionals and patients with identifying food options for patients with ARFID. </p>
      {!response && (
        <form onSubmit={handleSubmit}>
          {step === 1 && (
            <div>
              <TextField
                label="Enter the foods the patient likes"
                multiline
                value={patientLikes}
                onChange={(e) => setPatientLikes(e.target.value)}
                placeholder="Enter foods the patient likes"
                rows={4}
                col={50}
              />
              <Stack enabledScopeSelectors horizontal horizontalAlign="right" tokens={smallTokens}>
                <PrimaryButton onClick={() => setStep(2)}>Next</PrimaryButton>
              </Stack>
            </div>
          )}
          {step === 2 && (
            <div>
              <TextField
                label="Enter the foods the patient dislikes"
                multiline
                value={patientDislikes}
                onChange={(e) => setPatientDislikes(e.target.value)}
                placeholder="Enter foods the patient dislikes"
                rows={4}
                col={50}
              />
              <Stack enabledScopeSelectors horizontal horizontalAlign="right" tokens={smallTokens}>
                <DefaultButton onClick={() => setStep(1)}>Back</DefaultButton>
                <PrimaryButton onClick={() => setStep(3)}>Next</PrimaryButton>
              </Stack>
            </div>
          )}
          {step === 3 && (
            <div>
              <TextField
                label="Enter any other foods restrictions the patient has"
                multiline
                value={patientAllergies}
                onChange={(e) => setPatientAllergies(e.target.value)}
                placeholder="Enter foods the patient cannot have"
                rows={4}
                col={50}
              />
              <Stack enabledScopeSelectors horizontal horizontalAlign="right" tokens={smallTokens}>
                <DefaultButton onClick={() => setStep(2)}>Back</DefaultButton>
                <PrimaryButton type="submit">Submit</PrimaryButton>
              </Stack>
            </div>
          )}
        </form>)}
      {
        response && !loading && (
          <form onSubmit={handleUpdateSubmit}>
            <DetailsList
              items={items}
              columns={columns}
              setKey="set"
              selection={emptySelection}
              selectionPreservedOnEmptyClick={true}
              ariaLabelForSelectionColumn="Toggle selection"
              checkButtonAriaLabel="select row"
            />
            <div>
              <TextField
                label="How would you like to improve the recommendations?"
                multiline
                value={update}
                onChange={(e) => setUpdate(e.target.value)}
                placeholder="Please enter your feedback to get a better recommendation"
                rows={4}
                col={50}
              />
              <Stack enabledScopeSelectors horizontal horizontalAlign="right" tokens={smallTokens}>
                <PrimaryButton type="submit">Submit</PrimaryButton>
              </Stack>
            </div>
          </form>
        )
      }
      {loading && <Spinner size={SpinnerSize.large} />}
    </div>
  );
}

export default App
