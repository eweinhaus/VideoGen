import React from "react"
import { uploadStore } from "@/stores/uploadStore"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"

const AGE = ["child","teen","early_20s","mid_20s","late_20s","30s","40s","50s","60plus"]
const GENDER = ["masculine","feminine","androgynous","unspecified"]
const HAIR_COLOR = ["black","dark_brown","brown","light_brown","blonde","red","gray","white","unknown"]
const HAIR_STYLE = ["buzzed","short_straight","short_wavy","medium_curly","long_straight","long_wavy","bald","shaved","ponytail","afro","locs"]
const EYE_COLOR = ["brown","dark_brown","hazel","green","blue","gray","amber","unknown"]
const SKIN_TONE = ["very_fair","fair","medium","tan","brown","dark_brown","deep"]
const BUILD = ["slim","average","athletic","muscular","heavyset","unspecified"]
const HEIGHT = ["short","average","tall","unspecified"]
const STYLE = ["photo_realistic","anime","cartoon","3d","illustration","unknown"]

export function CharacterAnalysisReview() {
  const { characterAnalysisStatus, characterAnalysisEdited, characterAnalysisResult, setCharacterAnalysisEdited } = uploadStore()
  const analysis = characterAnalysisEdited

  if (characterAnalysisStatus === "processing") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Analyzing Character Image...</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Extracting visual features. This usually takes under 30 seconds.</div>
        </CardContent>
      </Card>
    )
  }

  if (characterAnalysisStatus !== "ready" || !analysis) {
    return null
  }

  const confidenceColor = analysis.confidence_binned === "high" ? "bg-green-500" : analysis.confidence_binned === "medium" ? "bg-yellow-500" : "bg-red-500"

  const set = (partial: Partial<typeof analysis>) => {
    setCharacterAnalysisEdited({ ...analysis, ...partial })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-3">
          Character Analysis Review
          <Badge className={`${confidenceColor} text-white`}>{analysis.confidence_binned}</Badge>
          <span className="text-sm text-muted-foreground">confidence {(analysis.confidence * 100).toFixed(0)}%</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Age Range</label>
          <Select value={analysis.age_range} onValueChange={(v) => set({ age_range: v as any })}>
            <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>{AGE.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Gender Presentation</label>
          <Select value={analysis.gender_presentation} onValueChange={(v) => set({ gender_presentation: v as any })}>
            <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>{GENDER.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Hair Color</label>
          <Select value={analysis.hair_color} onValueChange={(v) => set({ hair_color: v as any })}>
            <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>{HAIR_COLOR.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Hair Style</label>
          <Select value={analysis.hair_style} onValueChange={(v) => set({ hair_style: v as any })}>
            <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>{HAIR_STYLE.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Eye Color</label>
          <Select value={analysis.eye_color} onValueChange={(v) => set({ eye_color: v as any })}>
            <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>{EYE_COLOR.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Skin Tone</label>
          <Select value={analysis.skin_tone} onValueChange={(v) => set({ skin_tone: v as any })}>
            <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>{SKIN_TONE.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Build</label>
          <Select value={analysis.build} onValueChange={(v) => set({ build: v as any })}>
            <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>{BUILD.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Height</label>
          <Select value={analysis.height_bucket} onValueChange={(v) => set({ height_bucket: v as any })}>
            <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>{HEIGHT.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Style</label>
          <Select value={analysis.style} onValueChange={(v) => set({ style: v as any })}>
            <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>{STYLE.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-2 md:col-span-2">
          <label className="text-sm font-medium">Clothing (comma-separated)</label>
          <Input
            value={(analysis.clothing || []).join(",")}
            onChange={(e) => set({ clothing: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })}
            placeholder="hoodie, jeans"
          />
        </div>
        <div className="text-xs text-muted-foreground md:col-span-2">
          Identity features are enforced across scenes. Clothing/accessories are flexible unless you lock them via editing.
        </div>
      </CardContent>
    </Card>
  )
}


